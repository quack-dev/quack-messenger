#-*- encoding: utf-8 -*-
import random #because usernames
import os, sys
import time
from socket import *
import hashlib
from datetime import datetime
import thread

def random_username():
	mode1 = 'cvcvvc'
	mode2 = 'vccvv'
	vowels = 'aeiou'
	consonants = 'bcdfghjklmnpqrstwvxyz'
	mode = random.choice([mode1, mode2])
	username = "".join([random.choice(vowels) if i == "v" else random.choice(consonants) for i in mode])
	return username[0].upper() + username[1:]

def md5(i):
	#hashlib.md5 returns a very inconvenient format, so I'm just converting it to readable
	return hashlib.md5(i).digest().encode("hex")

def pad(text, length, pad = " ", minimum = False):
	#Makes string text given length by appending the pad until it is proper length
	#or, if the string is too long, it will just be cut off at length
	#if minimum = True, then the goal is as short a string as possible -- the input would
	#only be cut off, not padded to.
	if minimum and len(text) < length:
		return text
	if len(text) > length:
		if length > 10:
			return text[:length - 3] + "..."
		return text[:length]
	else:
		return text + (pad * (length - len(text)))

class Message(object):
	#the object that is used to organize messages, both incoming and outgoing.
	def __init__(self, text, m_from = None, m_to = None, m_time = None):
		if m_from == None and m_to == None: #being initialized from a __repr__ string
			data = text[1:-1].split(";")
			self.text = data[0].decode("base64")
			self.m_from = data[1].decode("base64")
			self.m_to = data[2].decode("base64")
			self.time = float(data[3])
		else:
			self.text = text
			self.m_from = m_from
			self.m_to = m_to
			#a time can be specified, but if it is not it will be set to the time the Message object is created
			self.time = m_time if m_time != None else time.time()
	def __repr__(self):
		return "{%s;%s;%s;%s}" % (self.text.encode("base64"), self.m_from.encode("base64"), self.m_to.encode("base64"), self.get_time())
	def get_time(self):
		return pad(str(self.time), 13, "0")

class Messenger(object):
	def __init__(self):
		########################################
		#            initial config            #
		#             (constants)              #
		########################################
		with open("messenger.config.txt", "r") as f:
			config_text = f.read()
		config = {}
		#read all non-empty lines
		for i in [n for n in config_text.split("\n") if len(n) > 0]:
			w = i.split(" ")
			#Using # as the comment
			if i[0] != "#":
				config[w[0]] = " ".join(w[1:])
		#look for a username in the config file. If it's not there, make one up
		if "username" in config.keys():
			self.username = config["username"]
		else:
			self.username = random_username()
		
		#the port for cummunications
		self.port = 13000
		if "port" in config.keys():
			self.port = int(config["port"])
		
		if not "width" in config.keys():
			self.width = 79
		else:
			self.width = int(config["width"])
		
		if not "height" in config.keys():
			self.height = 25
		else:
			self.height = int(config["height"])
		
		self.contacts = {}
		self.online_users = {} #self.online_users[username] = last time isalive ping has been received from them. Misleading: to get all users _currently_ online, use self.get_online_users()
		self.last_alive_sent_to = {} #last time an isalive ping was sent to a user
		self.update_contacts() #read the conversations folder and update/create self.contacts
		self.confirmed_messages = [] #list of hashes of messages that were received by their recipients
		
		#############################
		# set up initial conditions #
		#############################
		self.keep_alive = True #keeps all the threads going until it's set to False in self.exit
		self.window = "MAIN" #how self.reload_screen knows which screen to display
		self.muted = True #decides whether or not notification sound will play. Configure with /mute and /unmute
		self.isalive_max_wait = 60 #how long between isalive pings that the user is still online
		
		#############################
		#       start running       #
		#############################
		thread.start_new_thread(self.loop_receive, ())
		self.send_isalive(None, True)
		self.reload_screen()
		self.loop_input()
	
	def update_contacts(self):
		#contact list is based on people that there are conversation files for
		#this routine is used regularly to update the contact list, and is originally used to initialize the variables as well
		for root, dirs, files in os.walk("conversations"):
			contacts = []
			for filename in files:
				contacts.append(".".join(filename.split(".")[:-1])) #take out the file extension
		self.contacts = {}
		for contact in contacts:
			self.contacts[contact] = self.user_file_operation(contact, "r").split("\n")[0] #reads the first line of the conversation file -- the IP
			if contact not in self.online_users.keys():
				self.online_users[contact] = 0
				self.last_alive_sent_to[contact] = 0 #initialize the dict
	
	def get_ip(self, username, try2 = False):
		#lil bit of error handling, mostly this is a function for future modulability
		self.update_contacts()
		if username in self.contacts.keys():
			return self.contacts[username]
		else:
			if try2:
				return None
			else:
				time.sleep(.1)
				return self.get_ip(username, True)
	
	def get_username(self, ip):
		#not used anywhere (as of version beta-1.2)
		for key in self.contacts.keys():
			if self.contacts[key] == ip:
				return key
		return None
	
	def get_online_users(self):
		#have a ping in the last however many seconds
		return [i for i in self.online_users.keys() if time.time() - self.online_users[i] < self.isalive_max_wait]
	
	def user_file_operation(self, username, mode, text = None):
		#packaged way to read from and write to convo files
		filepath = os.path.join("conversations", "%s.txt" % (username))
		if mode == "r":
			with open(filepath, "r") as f:
				return f.read().replace("\r", "")
		else:
			with open(filepath, mode) as f:
				f.write(text)
			return None
	
	def exit(self):
		self.keep_alive = False
		exit()
	
	def reload_screen(self):
		if self.window == "MAIN":
			self.disp_main()
		elif self.window[:5] == "CONVO":
			self.disp_convo(self.window[6:])
	
	def write_to_convo_file(self, message, ip, read = None): #'read' modes are " " = normal, "*" = unread, "~" = unsent
		if read == None:
			if message.m_to == self.username: #if it just got sent to this user, it's unread. If it just got sent, is has been (by the sender)
				read = "*"
			else:
				read = " "
		self.update_contacts()
		#####################################################
		#              Anti-Duplicate Messages              #
		# this is the routine to prevent duplicate messages #
		# from appearing. Duplicates occur when a message   #
		# is sent and received, but the verification is not #
		# received by the sender. Duplicates are recognized #
		# by having the same timestamp and text as the most #
		# recent message.                                   #
		#####################################################
		
		is_duplicate = True #guilty until proven innocent
		
		if message.m_to == self.username: #this makes every message sent and received to yourself seen as "receiving"
			mode = "receiving"            #but that's okay, messaging yourself is really only for debugging, and you
		else:                             #can only tell in the convo file anyway
			mode = "sending"
		
		other_user = message.m_from if mode == "receiving" else message.m_to #used to find what convo file to write to, among other things
		
		if other_user in self.contacts.keys(): #if there is a conversation file and an ip
			last_message = [i for i in self.user_file_operation(other_user, "r").split("\n") if len(i) > 0][-1] #most recent message
			if "<<<" not in last_message and ">>>" not in last_message: #basically if there are no messages
				is_duplicate = False
			elif last_message[14:17] == ">>>" and mode == "receiving":
				is_duplicate = False
			elif last_message[14:17] == "<<<" and mode == "sending":
				is_duplicate = False
			else:
				m_time = float(last_message[1:14])
				text = last_message[17:]
				if message.time != m_time or text != message.text:
					is_duplicate = False
		else: #if there's no file, then the file is new, is not a duplicate
			is_duplicate = False
		
		do_reload = False
		if not is_duplicate:
			if other_user not in self.contacts.keys(): #if this is a new user, have to create a file for them
				self.user_file_operation(other_user, "w", ip + "\n")
			#regardless of whether or not they're new, add the message
			message_time = message.get_time()
			if mode == "receiving":
				self.user_file_operation(other_user, "a", read + message_time + "<<<" + message.text + "\n")
			else:
				self.user_file_operation(other_user, "a", read + message_time + ">>>" + message.text + "\n")
			if self.window == "CONVO-%s" % (other_user) or self.window == "MAIN":
				do_reload = True
			
			self.update_contacts()
			if mode == "receiving":
				self.notify()
		return do_reload
		
	
	def loop_receive(self):
		while self.keep_alive:
			self.receive()
	
	def loop_input(self):
		ipt = raw_input()
		while self.keep_alive:
			if len(ipt) > 0: #empty input would crash when checking ipt[0], so divert to just self.reload_screen()
				if ipt[0] == "/": #commands
					"""##############################################################################################################
					#                                              / Commands                                                       #
					#                                                                                                               #
					# /main                                    go to main window                                                    #
					# /exit                                    exit program                                                         #
					# /newmessage [username] [ip] [message]    send a new message to [username] at [ip]. Spaces okay in message     #
					# /resend                                  gives the option to resend unsent messages in a conversation window  #
					# /bell                                    send a bell character (\x07), it's not logged anywhere               #
					# /mute                                    mute notifications (doesn't work against /bell)                      #
					# /unmute                                  unmute notifications                                                 #
					# /alive                                   send isalive pings to all contacts                                   #
					# /[username]                              switch to [username] conversation screen                             #
					#                                                                                                               #
					##############################################################################################################"""
					cmd = ipt[1:]
					if cmd.lower() == "main":
						self.disp_main()
					elif cmd in self.contacts:
						self.disp_convo(cmd)
					elif cmd.lower() == "exit":
						self.exit()
					elif cmd.split(" ")[0].lower() == "newmessage":
						data = cmd.split(" ")
						m_to = data[1]
						ip = data[2]
						text = " ".join(data[3:])
						self.new_message(m_to, ip, text)
					elif cmd == "resend":
						if self.window[:5] == "CONVO":
							m_to = self.window[6:]
							raw = self.user_file_operation(m_to, "r")
							num_unsent = [i[0] for i in raw.split("\n") if len(i) > 0].count("~")
							sys.stdout.write("\rAttempt to resend %s messages? " % num_unsent)
							ipt = raw_input()
							if ipt.lower() == "yes" or ipt.lower() == "y":
								#info is already read, so delete all lines that are unsent. If they remain unsent, they will be rewritten
								raw = [i for i in raw.split("\n") if len(i) > 0]
								unsent_messages_raw = [i for i in raw if i[0] == "~"]
								sent_messages = [i for i in raw if i[0] != "~"] + [""]
								self.user_file_operation(m_to, "w", "\n".join(sent_messages))
								#exit()
								for m in unsent_messages_raw:
									text = m[17:]
									message = Message(text, self.username, m_to)
									self.send(message)
								self.reload_screen()
							else:
								self.reload_screen()
					elif cmd == "bell":
						if self.window[:5] == "CONVO":
							m_to = self.window[6:]
							self.send(Message("\x07", self.username, m_to))
						else:
							self.reload_screen()
					elif cmd == "mute":
						self.muted = True
						self.reload_screen()
					elif cmd == "unmute":
						self.muted = False
						self.reload_screen()
					elif cmd.split(" ")[0] == "alive":
						data = cmd.split(" ")
						if len(data) > 1:
							user = data[1]
							if user in self.contacts.keys():
								self.send_isalive(user, True)
						else:
							self.send_isalive(None, True)
						self.reload_screen()
					elif cmd in self.contacts.keys():
						self.window = "CONVO-%s" % (cmd)
						self.reload_screen()
					else: #in case the command was botched
						self.reload_screen()
						error_message = "\r***\"%s\" is not a command***" % (cmd.split(" ")[0])
						sys.stdout.write(pad(error_message, self.width, " "))
						time.sleep(2)
						print
						self.reload_screen()
				else: #send a message, or switch windows if screen is main
					if self.window[:5] == "CONVO":
						self.send(Message(ipt, self.username, self.window[6:]))
					elif ipt in self.contacts.keys():
						self.disp_convo(ipt)
					else:
						self.reload_screen()
			else:
				self.reload_screen()
			ipt = raw_input()
	
	def receive_skeleton(self):
		#most basic UDP receive
		host = ""
		buf = 1024
		addr = (host, self.port)
		UDPSock = socket(AF_INET, SOCK_DGRAM)
		UDPSock.bind(addr)
		(m, addr) = UDPSock.recvfrom(buf)
		UDPSock.close()
		return m, addr
	
	def receive(self):
		#remains open indefinitely, returns text and host information when something is received
		m, addr = self.receive_skeleton()
		
		do_reload = False
		
		###########################################################################
		#                            types of messages                            #
		# * - reflexive isalive ping (sent automatically)                         #
		# ! - prime isalive ping (sent on startup or by /alive)                   #
		# $ - verification message (verifies that a sent message was received)    #
		###########################################################################
		
		####isalive condition####
		isaliveping = False
		force_isalive_response = False
		if m[0] == "*" or m[0] == "!":
			if m[0] == "!":
				force_isalive_response = True
			isaliveping = True
			m = m[1:]
		
		####verification####
		if m[0] == '$': #verification message received
			m = m[1:].decode("base64")
			message = Message(m)
			self.confirmed_messages.append(message.text) #message.text is the md5 hash of the message waiting to be verified
			self.online_users[message.m_from] = time.time()
			self.reload_screen()
			return
		
		####general handling####
		message = Message(m.decode("base64"))
		if not isaliveping:
			#normal messages
			thread.start_new_thread(self.send_verification, (Message(md5(m), self.username, message.m_from),))
		if message.m_from in self.last_alive_sent_to:
			if time.time() - self.last_alive_sent_to[message.m_from] > 20 or force_isalive_response: #if it's been awhile since you've told this user you're online.
				thread.start_new_thread(self.send_isalive, (message.m_from,))                        #substitute for the infinte looping that caused everything to run slowly
		previously_online = self.get_online_users()
		self.online_users[message.m_from] = time.time()
		
		if message.text == "\x07":
			print "\x07" #ding
			self.reload_screen()
			return
		
		currently_online = self.get_online_users()
		new_online = [i for i in currently_online if not i in previously_online]
		new_offline = [i for i in previously_online if not i in currently_online]
		state_changed = new_online + new_offline
		if (self.window == "MAIN" and (len(state_changed) > 0)) or (self.window.replace("CONVO-", "") in state_changed):
			#reload if any users changed state and the program is on the main screen OR if the user whose conversation window the program is on changed state
			do_reload = True
		if not isaliveping:
			do_reload = self.write_to_convo_file(message, addr[0]) or do_reload
		if do_reload:
			self.reload_screen()
	
	def disp_main(self):
		self.update_contacts()
		self.window = "MAIN"
		disp_string = "\nContacts"
		disp_string += "\n" + "="*self.width
		body_size = self.height - 3
		contact_disp = []
		current_online_users = self.get_online_users()
		for contact in self.contacts.keys():
			num_unread = [i[0] for i in self.user_file_operation(contact, "r").split("\n") if len(i) > 0].count("*") #counts the number if asterisks in the file that are one the first line
			contact_line = ("*" if contact in current_online_users else " ") #mark if they're online
			contact_line += contact
			contact_line += (" (%s)" % (num_unread) if num_unread > 0 else "") #if there's an unread number, put that after the contact name
			contact_disp.append(contact_line)
		if len(contact_disp) <= body_size:
			disp_string += "\n" + "\n".join(contact_disp + [""]*(body_size - len(contact_disp))) #make it at least enough lines to fill the window
		else:
			disp_string += "\n" + "\n".join(contact_disp[-body_size:]) #or truncate if it's too long. Temporary until scrolling is implemented
		disp_string += "\n<%s>" % (self.username) #input line
		sys.stdout.write(disp_string)
	
	def convo_line(self, message):
		#makes a printable conversation line from a message object
		user = message.m_from #messages are displayed by who sent them
		m_time = message.time
		text = message.text
		now = datetime.fromtimestamp(time.time())
		then = datetime.fromtimestamp(m_time) #when the message was sent
		if datetime.strftime(now, "%m/%d") == datetime.strftime(then, "%m/%d"): #if this message was sent today...
			timestr = datetime.strftime(datetime.fromtimestamp(m_time), "%H:%M") #only show hour and minute
		else:
			timestr = datetime.strftime(datetime.fromtimestamp(m_time), "%m/%d %H:%M") #otherwise show date and time
		#these messages are given a special attribute before they're passed to this function: read. Message.read = "*" for unread, " " for read, and "~" for unsent
		line = "%s%s <%s> %s" % (message.read.replace(" ", ""), timestr, user, text)
		lines = [line]
		#while the last line is longer than it should be, make it the right size
		while len(lines[-1]) > self.width:
			lines = lines[0:-1] + [lines[-1][:self.width], lines[-1][self.width:]]
		lines = map(lambda x: pad(x, self.width), lines) #pad all the lines
		return "\n".join(lines)
	
	def disp_convo(self, m_from):
		self.window = "CONVO-%s" % (m_from)
		messagefiletext = self.user_file_operation(m_from, "r").split("\n")[1:] #split by line, and disclude the first line (the IP)
		buf_messages = [i for i in messagefiletext if len(i) > 0][-(self.height - 3):] #Get everything that can be displayed, but only however many lines can fit one-screen
		
		head_line = ("Conversation with %s" % (m_from)) + (" (inactive/offline)" if not m_from in self.get_online_users() else "") + "\n" + pad("", self.width, "=")
		#fill conversation window to height - 3 lines
		message_objects = []
		for raw_message in buf_messages:
			m_time = float(raw_message[1:14])
			text = raw_message[17:]
			if raw_message[14:17] == "<<<":
				message_objects.append(Message(text, m_from, self.username, m_time))
			elif raw_message[14:17] == ">>>":
				message_objects.append(Message(text, self.username, m_from, m_time))
			message_objects[-1].read = raw_message[0]
		messages = "\n".join(self.convo_line(i) for i in message_objects)
		disp_messages = messages.split("\n")[-(self.height - 3):]
		if len(disp_messages) < self.height - 3:
			disp_messages = disp_messages + [""] * ((self.height - 3) - len(disp_messages))
		disp_messages = "\n".join(disp_messages)
		full_string = "\n".join([head_line, disp_messages])
		full_string += "\n<%s>" % (self.username)
		sys.stdout.write("\r" + full_string)
		current_convofile = self.user_file_operation(m_from, "r")
		self.user_file_operation(m_from, "w", current_convofile.replace("\n*", "\n ")) #mark everything as read
	
	def send_skeleton(self, host, data):
		#the most basic of basic UDP sending
		#~ try: tk uncomment
		addr = (host, self.port)
		UDPSock = socket(AF_INET, SOCK_DGRAM)
		UDPSock.sendto(data, addr)
		UDPSock.close()
		#~ except:
	
	def send(self, message):
		host = self.get_ip(message.m_to)
		
		did_send = False
		tries = 0
		max_tries = 4
		time_per_try = 6
		
		#this stuff is for the Sending... 'animation'
		change = .5 #how often it's changed
		dotcount = [0, 1, 2, 3] #the number of dots after send. Order repeats
		dotindex = dotcount.index(max(dotcount)) #start with the largest number of dots. Idk why but it feels right
		self.update_contacts() #reverts to pre-message-sending contacts list
		if message.m_to not in self.contacts:
			self.user_file_operation(message.m_to, "w", host + "\n")
			self.update_contacts()
		self.disp_convo(message.m_to)
		sys.stdout.write("\rSending" + ("." * dotcount[dotindex]) + ("\x00" * (max(dotcount) - dotcount[dotindex])))
		#this while loop sends x number of times
		while not did_send and tries < max_tries:
			self.send_skeleton(self.get_ip(message.m_to), message.__repr__().encode("base64"))
			time_sent = time.time()
			#this just does the animation until verification is received
			while not md5(message.__repr__().encode("base64")) in self.confirmed_messages and time.time() - time_sent < time_per_try:
				dotindex = int((time.time() - time_sent) / change) % len(dotcount)
				if tries != 0:
					sys.stdout.write("\rSending (try %s/%s)" % (tries + 1, max_tries) + ("." * dotcount[dotindex]) + ("\x00" * (max(dotcount) - dotcount[dotindex])))
				else:
					sys.stdout.write("\rSending" + ("." * dotcount[dotindex]) + ("\x00" * (max(dotcount) - dotcount[dotindex])))
				time.sleep(.01)
			#check if while loop exited because it was actually verified
			if md5(message.__repr__().encode("base64")) in self.confirmed_messages:
				did_send = True
			if did_send:
				if message.text != "\x07":
					self.write_to_convo_file(message, self.get_ip(message.m_to))
				self.disp_convo(message.m_to)
				return
			tries += 1
		if tries == max_tries:
			sys.stdout.write("\rmessage failed to send:(")
			time.sleep(2)
			if message.text != "\x07":
				self.write_to_convo_file(message, self.get_ip(message.m_to), "~")
			self.disp_convo(message.m_to)
	
	def send_verification(self, message):
		time.sleep(1)
		host = self.get_ip(message.m_to)
		
		self.send_skeleton(host, "$" + message.__repr__().encode("base64"))
	
	def new_message(self, m_to, ip, text):
		message = Message(text, self.username, m_to)
		self.contacts[m_to] = ip #so that generic send can find it
		self.send(message)
	
	def notify(self):
		if not self.muted:
			print "\x07"
			self.reload_screen()
	
	def send_isalive(self, user = None, force_response = False):
		if not force_response:
			time.sleep(10) #tk this sucks
		if user == None:
			contacts_to_ping = self.contacts.keys()
		else:
			contacts_to_ping = [user]
		for i in range(2): #these aren't being verified, so best to send two
			for contact in contacts_to_ping:
				message = Message("*", self.username, contact)
				prefix = "!" if force_response else "*"
				data = prefix + message.__repr__().encode("base64")
				if contact != contacts_to_ping[-1]:
					thread.start_new_thread(self.send_skeleton, (self.get_ip(message.m_to), data))
				else:
					self.send_skeleton(self.get_ip(message.m_to), data)
				self.last_alive_sent_to[contact] = time.time()
		time.sleep(.2)

if __name__ == "__main__":
	Messenger()
