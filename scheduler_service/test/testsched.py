#!/usr/bin/python
from scheduler_service.util.singletonlite import mongoClient
from scheduler_service.algorithm.schedmaster import SchedMaster
import logging
from scheduler_service.external.message import RabbitInterface

def main():
    #logging.basicConfig(filename='debug.log', filemode='w', level=logging.INFO)
    logging.basicConfig(level=logging.DEBUG)
    '''
    schedMaster = SchedMaster(mongoClient, "rrdb", "ph", "PHMSA",
        "M2014")
    dbstatus = schedMaster.generate()
    '''
    rabbitInterface = RabbitInterface()
if __name__ == '__main__':
    main()
