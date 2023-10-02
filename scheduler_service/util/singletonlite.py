#!/usr/bin/python
''' Copyright Carbonyl LLC 2023 and YukonTR 2014 '''
# singleton effects by utilizing module import
# ref http://stackoverflow.com/questions/10936709/why-does-a-python-module-act-like-a-singleton
import socket
from pymongo import MongoClient
from scheduler_service.db.dbinterface import MongoDBInterface
from time import asctime


if socket.gethostname() == 'web380.production.com':
    mongoClient = MongoClient('localhost', 11466)
    hostserver = "production"
else:
    mongoClient = MongoClient('localhost', 27017)
    hostserver = "local"
generic_dbInterface = MongoDBInterface(mongoClient)
creation_time = asctime()
