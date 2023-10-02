#!/usr/bin/python
''' Copyright Carbonyl LLC 2023 and YukonTR 2014'''
from scheduler_service.db.dbinterface import DB_Col_Type
from scheduler_service.db.basedbinterface import BaseDBInterface

class PrefDBInterface(BaseDBInterface):
    def __init__(self, mongoClient, userid_name, newcol_name, sched_cat):
        BaseDBInterface.__init__(self, mongoClient, userid_name,
            newcol_name, sched_cat,
            DB_Col_Type.PreferenceInfo, 'PREF_ID')

    def write_constraint_status(self, cstatus_list):
        operator = "$set"
        for cstatus in cstatus_list:
            query_obj = {'PREF_ID':cstatus['pref_id']}
            operator_obj = {'SATISFY':cstatus['status']}
            self.dbinterface.updatedoc(query_obj, operator, operator_obj)
