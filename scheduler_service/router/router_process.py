#!/usr/bin/python
''' Copyright Carbonyl LLC 2023 and YukonTR 2014
This file includes functions to route incoming requests from client.
Utilizes bottle route infrastructure '''
from fastapi import FastAPI, Request, APIRouter, Path, Query, HTTPException
import simplejson as json
import time
from pprint import pprint
import networkx as nx
from networkx.readwrite import json_graph
from networkx import connected_components
from scheduler_service.algorithm.matchgenerator import MatchGenerator
from scheduler_service.db.dbinterface import MongoDBInterface, DB_Col_Type
import logging
from scheduler_service.util.singletonlite import mongoClient, hostserver, generic_dbInterface, creation_time
from scheduler_service.db.tourndbinterface import TournDBInterface
from scheduler_service.db.fielddbinterface import FieldDBInterface
from scheduler_service.db.rrdbinterface import RRDBInterface
from scheduler_service.algorithm.schedmaster import SchedMaster
from scheduler_service.algorithm.tournschedmaster import TournSchedMaster
from scheduler_service.db.scheddbinterface import SchedDBInterface
from scheduler_service.db.prefdbinterface import PrefDBInterface
from scheduler_service.db.teamdbinterface import TeamDBInterface
from scheduler_service.db.conflictdbinterface import ConflictDBInterface
from scheduler_service.db.userdbinterface import UserDBInterface
from scheduler_service.util.sched_exceptions import CodeLogicError
from scheduler_service.util.xls_exporter import XLS_Exporter
from operator import itemgetter

router = APIRouter()


class RouteLogic:
    '''ref http://stackoverflow.com/questions/8725605/bottle-framework-and-oop-using-method-instead-of-function and
    https://www.artima.com/weblogs/viewpost.jsp?thread=240808
    http://www.jeffknupp.com/blog/2013/11/29/improve-your-python-decorators-explained/
    for decorator related tutorials and integrating bottle with methods.
    '''

    def __init__(self):
        self.dbinterface_map_list = list();
        self.dbindexerMatch = lambda x, y, z: [i for i, p in enumerate(
            self.dbinterface_map_list) if p['userid_name'] == x and p['db_type'] == y
                                               and p['sched_cat'] == z]
        self.schedmaster_map_list = list();
        self.sindexerMatch = lambda x, y: [i for i, p in
                                           enumerate(self.schedmaster_map_list) if p['userid_name'] == x and
                                           p['sched_cat'] == y]


_routelogic_obj = RouteLogic()

'''
references
http://www.tutorial.useiis7.net/dojodoc/001/
http://myadventuresincoding.wordpress.com/2011/01/02/creating-a-rest-api-in-python-using-bottle-and-mongodb/
http://gotofritz.net/blog/weekly-challenge/restful-python-api-bottle/
http://bottlepy.org/docs/dev/tutorial.html#request-routing
'''


# create new db collection based on new schedule parameters (currently for tournament format)
@router.get('/create_newdbcol/{userid_name}/{db_type}/{newcol_name}/{sched_cat}')
def create_newdbcol(request: Request, userid_name, db_type, newcol_name, sched_cat):
    callback_name = request.query_params.get("callback")
    info_data = request.query_params.get("info_data")
    # variables intended to be scalar ints should be converted from
    # ints that come across as strings over the wire back to int
    config_status = int(request.query_params.get("config_status"))
    dbInterface = select_db_interface(userid_name, db_type, newcol_name, sched_cat)
    if db_type == 'rrdb':
        oddnum_mode = int(request.query_params.get("oddnum_mode"))
        dbInterface.writeDB(info_data, config_status, oddnum_mode)
    elif db_type == 'tourndb':
        dbInterface.writeDB(info_data, config_status)
    elif db_type in ['fielddb', 'prefdb', 'teamdb', 'conflictdb']:
        # get divinfo parameters associated with fieldinfo obj
        divstr_colname = request.query_params.get("divstr_colname")
        divstr_db_type = request.query_params.get("divstr_db_type")
        dbInterface.writeDB(info_data, config_status,
                            divstr_colname=divstr_colname,
                            divstr_db_type=divstr_db_type)
    else:
        raise CodeLogicError("leaguedivprocess:create_newdbcol: db_type not recognized db_type=%s" % (db_type,))
    _routelogic_obj.dbinterface_map_list.append({'userid_name': userid_name,
                                                 'db_type': db_type, 'dbinterface': dbInterface,
                                                 'sched_cat': sched_cat})
    a = json.dumps({'test': 'divasdf'})
    return f"{callback_name}({a})"


# @route('/update_dbcol/<userid_name>/<db_type>/<col_name>/<sched_cat>')
@router.post('/update_dbcol/{userid_name}/{db_type}/{col_name}/{sched_cat}')
def update_dbcol(request: Request, userid_name, db_type, col_name, sched_cat):
    callback_name = request.query_params.get("callback")
    update_data_str = request.query_params.get("update_data")
    dbInterface = select_db_interface(userid_name, db_type, col_name, sched_cat)
    dbInterface.updateDB(update_data_str)
    a = json.dumps({'test': 'updateasdf'})
    return f"{callback_name}({a})"


# @route('/delete_dbcol/<userid_name>/<db_type>/<delcol_name>/<sched_cat>')
@router.delete('/delete_dbcol/{userid_name}/{db_type}/{delcol_name}/{sched_cat}')
def delete_dbcol(request: Request, userid_name, db_type, delcol_name, sched_cat):
    callback_name = request.query_params.get("callback")
    dbInterface = select_db_interface(userid_name, db_type, delcol_name,
                                      sched_cat)
    dbInterface.drop_collection()
    a = json.dumps({'test': 'sdg'})
    return f"{callback_name}({a})"


# @route('/get_dbcol/<userid_name>/<db_type>/<getcol_name>/<sched_cat>')
@router.get('/get_dbcol/{userid_name}/{db_type}/{getcol_name}/{sched_cat}')
def get_dbcol(request: Request, userid_name, db_type, getcol_name, sched_cat):
    callback_name = request.query_params.get("callback")
    dbInterface = select_db_interface(userid_name, db_type, getcol_name,
                                      sched_cat)
    # save as member of global routelogic object to be used in send_delta function
    sindex_list = _routelogic_obj.sindexerMatch(userid_name, sched_cat)
    if not sindex_list:
        _routelogic_obj.dbinterface_map_list.append({'userid_name': userid_name,
                                                     'db_type': db_type, 'dbinterface': dbInterface,
                                                     'sched_cat': sched_cat})
    if db_type == 'newscheddb':
        return_obj = {'param_obj': dbInterface.getschedule_param(),
                      'sched_status': dbInterface.getsched_status()}
    else:
        dbtuple = dbInterface.readDB()
        info_list = dbtuple.list
        idproperty = dbInterface.idproperty
        info_list.sort(key=itemgetter(idproperty))
        config_status = dbtuple.config_status
        return_obj = {'info_list': info_list, 'config_status': config_status}
        if db_type in ['fielddb', 'prefdb', 'teamdb', 'conflictdb']:
            # if db is fielddb, then append divinfo information also-
            # used as part of fieldinfo config on UI grid
            divstr_colname = dbtuple.divstr_colname
            divstr_db_type = dbtuple.divstr_db_type
            if divstr_colname and divstr_db_type:
                dbInterface = select_db_interface(userid_name, divstr_db_type,
                                                  divstr_colname, sched_cat)
                dbtuple = dbInterface.readDB()
                info_list = dbtuple.list
                idproperty = dbInterface.idproperty
                info_list.sort(key=itemgetter(idproperty))
                config_status = dbtuple.config_status
            else:
                info_list = []
                config_status = 0
                divstr_db_type = ""
                divstr_colname = ""
            divstr_obj = {'colname': divstr_colname, 'db_type': divstr_db_type,
                          'info_list': info_list, 'config_status': config_status}
            return_obj.update({'divstr_obj': divstr_obj})
    a = json.dumps(return_obj)
    return f"{callback_name}({a})"


# @route('/send_generate/<userid_name>/<sched_cat>')
@router.post('/send_generate/{userid_name}/{sched_cat}')
def send_generate(request: Request, userid_name: str, sched_cat: str):
    callback_name = request.query_params.get("callback")
    db_type = request.query_params.get("db_type")
    divcol_name = request.query_params.get("divcol_name")
    fieldcol_name = request.query_params.get("fieldcol_name")
    schedcol_name = request.query_params.get("schedcol_name")

    if not callback_name or not db_type or not divcol_name or not fieldcol_name or not schedcol_name:
        raise HTTPException(status_code=400, detail="Missing required query parameters")

    # if db_type == 'rrdb':
    if sched_cat == "L":
        prefcol_name = request.query_params.get("prefcol_name")

        conflictcol_name = request.query_params.get("conflictcol_name")

        schedMaster = SchedMaster(mongoClient, userid_name, db_type, divcol_name,
                                  fieldcol_name, schedcol_name, prefcol_name=prefcol_name,
                                  conflictcol_name=conflictcol_name)
        if not schedMaster.error_code:
            # save schedMaster to global obj to reuse on get_schedule
            # _routelogic_obj.schedmaster_map[userid_name] = schedMaster
            sindex_list = _routelogic_obj.sindexerMatch(userid_name, sched_cat)
            if sindex_list:
                sindex = sindex_list[0]
                _routelogic_obj.schedmaster_map_list[sindex]["schedmaster_obj"] = \
                    schedMaster
            else:
                _routelogic_obj.schedmaster_map_list.append(
                    {"userid_name": userid_name, "sched_cat": sched_cat,
                     "schedmaster_obj": schedMaster})
            dbstatus = schedMaster.generate()
            if dbstatus['status'] == 1 or (dbstatus['status'] == 0 and 'error_code' not in dbstatus):
                a = json.dumps({"dbstatus": dbstatus})
            else:
                a = json.dumps({"dbstatus": 0, "error_code": dbstatus['error_code'],
                                "error_message": dbstatus['error_message']})
        else:
            a = json.dumps({"error_code": schedMaster._error_code, "error_message": schedMaster._error_message})
            del schedMaster
    elif sched_cat == "T":
        tourn_type = request.query_params.get("tourn_type")

        schedMaster = TournSchedMaster(mongoClient, userid_name, divcol_name,
                                       fieldcol_name, schedcol_name, tourn_type)
        if not schedMaster.error_code:
            # save schedMaster to global obj to reuse on get_schedule
            # _routelogic_obj.schedmaster_map[userid_name] = schedMaster
            sindex_list = _routelogic_obj.sindexerMatch(userid_name, sched_cat)
            if sindex_list:
                sindex = sindex_list[0]
                _routelogic_obj.schedmaster_map_list[sindex]["schedmaster_obj"] = \
                    schedMaster
            else:
                _routelogic_obj.schedmaster_map_list.append(
                    {"userid_name": userid_name, "sched_cat": sched_cat,
                     "schedmaster_obj": schedMaster})
            dbstatus = schedMaster.schedGenerate()
            a = json.dumps({"dbstatus": dbstatus})
        else:
            a = json.dumps({"error_code": schedMaster._error_code})
            del schedMaster
    else:
        raise CodeLogicError("RouteProcess:SendGenerate, Invalid Sched Cat=%s" %
                             (sched_cat,))
    return f"{callback_name}({a})"


# @route('/send_delta/<userid_name>/<col_name>/<action_type>/<field_id:int>/<sched_cat>')
@router.post('/send_delta/{userid_name}/{col_name}/{action_type}/{field_id:int}/{sched_cat}')
def send_delta(request: Request, userid_name, col_name, action_type, field_id, sched_cat):
    callback_name = request.query_params.get("callback")
    dbindex_list = _routelogic_obj.dbindexerMatch(userid_name, 'fielddb', sched_cat)
    if dbindex_list:
        dbindex = dbindex_list[0]
        dbInterface = _routelogic_obj.dbinterface_map_list[dbindex]['dbinterface']
    else:
        dbInterface = select_db_interface(userid_name, 'fielddb', col_name,
                                          sched_cat)
    if action_type == 'remove':
        remove_str = request.query_params.get("remove_str")
        remove_list = [int(x) for x in remove_str.split(',')]
        # get dbinterface_obj assigned during create_newdbcol
        # send_data is always called from UI config grid, which generates either a
        # create_newdbcol or get_dbcol
        dbstatus = dbInterface.adjust_config(action_type, field_id, remove_list)
    elif action_type == 'change':
        change_str = request.query_params.get("change_str")
        change_list = json.loads(change_str)
        dbstatus = dbInterface.adjust_config(action_type, field_id, change_list)
    a = json.dumps({"dbstatus": dbstatus})


# @route('/get_schedule/<userid_name>/<schedcol_name>/<idproperty>/<propid:int>/<sched_cat>')
@router.get('/get_schedule/{userid_name}/{schedcol_name}/{idproperty}/{propid:int}/{sched_cat}')
def get_schedule(request: Request, userid_name, schedcol_name, idproperty, propid, sched_cat):
    callback_name = request.query_params.get("callback")
    # schedMaster = _routelogic_obj.schedmaster_map.get(userid_name)
    sindex_list = _routelogic_obj.sindexerMatch(userid_name, sched_cat)

    if sindex_list:
        sindex = sindex_list[0]
        schedMaster = _routelogic_obj.schedmaster_map_list[sindex]['schedmaster_obj']
        if len(sindex_list) > 1:
            logging.warning("RouteProcess:get_schedule, multiple indexermatch=%s" % (sindex_list,))
    else:
        schedMaster = None
    # else:
    #    raise CodeLogicError("RouteProcess:get_schedule, No indexermatch with routelogic=%s"
    #            % (_routelogic_obj.schedmaster_map_list,))
    if schedMaster is None:
        dbInterface = SchedDBInterface(mongoClient, userid_name, schedcol_name,
                                       sched_cat)
        param = dbInterface.getschedule_param()
        schedMaster = SchedMaster(mongoClient, userid_name, param['divdb_type'],
                                  param['divcol_name'], param['fieldcol_name'], schedcol_name,
                                  prefcol_name=param['prefcol_name'],
                                  conflictcol_name=param['conflictcol_name'])
        if not schedMaster.error_code:
            # save schedMaster to global obj to reuse on get_schedule
            # _routelogic_obj.schedmaster_map[userid_name] = schedMaster
            _routelogic_obj.schedmaster_map_list.append(
                {"userid_name": userid_name, "sched_cat": sched_cat,
                 "schedmaster_obj": schedMaster})
    if schedMaster.schedcol_name == schedcol_name:
        if idproperty == 'team_id' or idproperty == 'fair_id':
            # read query_params parameters if idprop is team_id - div_age and div_gen
            div_age = request.query_params.get("div_age")
            div_gen = request.query_params.get("div_gen")
            return_dict = schedMaster.get_schedule(idproperty, propid,
                                                   div_age=div_age, div_gen=div_gen)
        else:
            return_dict = schedMaster.get_schedule(idproperty, propid)
    else:
        return_dict = {}
    a = json.dumps(return_dict)
    return f"{callback_name}({a})"


# @route('/get_teamtable/<userid_name>/<schedcol_name>/<div_age>/<div_gen>/<team_id:int>/<sched_cat>')
@router.get('/get_teamtable/{userid_name}/{schedcol_name}/{div_age}/{div_gen}/{team_id:int}/{sched_cat}')
def get_teamtable(request: Request, userid_name, schedcol_name, div_age, div_gen, team_id, sched_cat):
    callback_name = request.query_params.get("callback")
    # schedMaster = _routelogic_obj.schedmaster_map.get(userid_name)
    sindex_list = _routelogic_obj.sindexerMatch(userid_name, sched_cat)
    if sindex_list:
        sindex = sindex_list[0]
        schedMaster = _routelogic_obj.schedmaster_map_list[sindex]['schedmaster_obj']
        if len(sindex_list) > 1:
            logging.warning("RouteProcess:get_teamtable, multiple indexermatch=%s" % (sindex_list,))
    else:
        schedMaster = None
        # raise CodeLogicError("RouteProcess:get_teamtable, No indexermatch with routelogic=%s"
        #        % (_routelogic_obj.schedmaster_map_list,))
    if schedMaster is None:
        dbInterface = SchedDBInterface(mongoClient, userid_name, schedcol_name,
                                       sched_cat)
        param = dbInterface.getschedule_param()
        schedMaster = SchedMaster(mongoClient, userid_name, param['divdb_type'],
                                  param['divcol_name'], param['fieldcol_name'], schedcol_name,
                                  prefcol_name=param['prefcol_name'],
                                  conflictcol_name=param['conflictcol_name'])
        if not schedMaster.error_code:
            # save schedMaster to global obj to reuse on get_schedule
            # _routelogic_obj.schedmaster_map[userid_name] = schedMaster
            _routelogic_obj.schedmaster_map_list.append(
                {"userid_name": userid_name, "sched_cat": sched_cat,
                 "schedmaster_obj": schedMaster})
    if schedMaster.schedcol_name == schedcol_name:
        return schedMaster.getHTMLTeamTable(div_age, div_gen, team_id)
    else:
        return_dict = {}
    a = json.dumps(return_dict)
    return f"{callback_name}({a})"


# @route('/get_xls/<userid_name>/<schedcol_name>/<db_type>/<genxls_id>/<sched_cat>')
@router.get('/get_xls/{userid_name}/{schedcol_name}/{db_type}/{genxls_id}/{sched_cat}')
def get_xls(request: Request, userid_name, schedcol_name, db_type, genxls_id, sched_cat):
    callback_name = request.query_params.get("callback")
    # schedMaster = _routelogic_obj.schedmaster_map.get(userid_name)
    sindex_list = _routelogic_obj.sindexerMatch(userid_name, sched_cat)
    if sindex_list:
        sindex = sindex_list[0]
        schedMaster = _routelogic_obj.schedmaster_map_list[sindex]['schedmaster_obj']
        if len(sindex_list) > 1:
            logging.warning("RouteProcess:get_xls, multiple indexermatch=%s" % (sindex_list,))
    else:
        schedMaster = None
        # raise CodeLogicError("RouteProcess:get_xls, No indexermatch with routelogic=%s"
        #        % (_routelogic_obj.schedmaster_map_list,))
    if schedMaster is None:
        dbInterface = SchedDBInterface(mongoClient, userid_name, schedcol_name,
                                       sched_cat)
        param = dbInterface.getschedule_param()
        # if db_type == 'rrdb':
        if sched_cat == "L":
            schedMaster = SchedMaster(mongoClient, userid_name, param['divdb_type'],
                                      param['divcol_name'], param['fieldcol_name'], schedcol_name,
                                      prefcol_name=param['prefcol_name'],
                                      conflictcol_name=param['conflictcol_name'])
        elif sched_cat == "T":
            schedMaster = TournSchedMaster(mongoClient, userid_name,
                                           param['divcol_name'], param['fieldcol_name'], schedcol_name)
        if not schedMaster.error_code:
            # save schedMaster to global obj to reuse on get_schedule
            # _routelogic_obj.schedmaster_map[userid_name] = schedMaster
            _routelogic_obj.schedmaster_map_list.append(
                {"userid_name": userid_name, "sched_cat": sched_cat,
                 "schedmaster_obj": schedMaster})
        else:
            del schedMaster
    if schedMaster.schedcol_name == schedcol_name:
        xls_exporter = schedMaster.xls_exporter
        if xls_exporter is None:
            xls_exporter = XLS_Exporter(schedcol_name,
                                        divinfo_tuple=schedMaster.divinfo_tuple,
                                        fieldinfo_tuple=schedMaster.fieldinfo_tuple,
                                        sdbInterface=schedMaster.sdbInterface)
            schedMaster.xls_exporter = xls_exporter
        # if db_type == 'tourndb':
        if sched_cat == "T":
            tourn_type = request.query_params.get("tourn_type")
            file_list = xls_exporter.export(genxls_id, db_type,
                                            tourn_type=tourn_type)
        else:
            file_list = xls_exporter.export(genxls_id, db_type)
        return_dict = {'file_list': file_list}
    else:
        return_dict = {}
    a = json.dumps(return_dict)
    return f"{callback_name}({a})"


# @route('/get_hostserver')
@router.get('/get_hostserver')
def get_hostserver(request: Request):
    callback_name = request.query_params.get("callback")
    a = json.dumps({"hostserver": hostserver, "creation_time": creation_time})
    return f"{callback_name}({a})"


# @route('/check_user/<userid_name>')
@router.get('/check_user/<userid_name>')
def check_user(request: Request, userid_name):
    callback_name = request.query_params.get("callback")
    dbInterface = UserDBInterface(mongoClient)
    result = dbInterface.check_user(userid_name)
    # userdb_list = generic_dbInterface.getUserCollection()
    # result = 1 if userid_name in userdb_list else 0
    a = json.dumps({'result': result})
    return f"{callback_name}({a})"


# @route('/create_user/<userid_name>')
@router.get('/create_user/<userid_name>')
def create_user(request: Request, userid_name):
    callback_name = request.query_params.get("callback")
    dbInterface = UserDBInterface(mongoClient)
    dbInterface.writeDB(userid_name)
    # dbInterface.simplewriteDB(userid_name)
    a = json.dumps({'result': 1})
    return f"{callback_name}({a})"


# @route('/get_dbcollection/<userid_name>')
@router.get('/get_dbcollection/<userid_name>')
def get_dbcollection(request: Request, userid_name):
    callback_name = request.query_params.get("callback")
    rrdbcol_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.RoundRobin, userid_name, "L") + \
                   generic_dbInterface.getScheduleCollection(
                       DB_Col_Type.RoundRobin, userid_name, "T")
    tourndbcol_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.TournRR, userid_name, "L") + \
                      generic_dbInterface.getScheduleCollection(
                          DB_Col_Type.TournRR, userid_name, "T")
    fielddb_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.FieldInfo, userid_name, "L") + \
                   generic_dbInterface.getScheduleCollection(
                       DB_Col_Type.FieldInfo, userid_name, "T")
    newscheddb_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.GeneratedSchedule, userid_name, "L") + \
                      generic_dbInterface.getScheduleCollection(
                          DB_Col_Type.GeneratedSchedule, userid_name, "T")
    prefdb_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.PreferenceInfo, userid_name, "L") + \
                  generic_dbInterface.getScheduleCollection(
                      DB_Col_Type.PreferenceInfo, userid_name, "T")
    teamdb_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.TeamInfo, userid_name, "L") + \
                  generic_dbInterface.getScheduleCollection(
                      DB_Col_Type.TeamInfo, userid_name, "T")
    conflictdb_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.ConflictInfo, userid_name, "L") + \
                      generic_dbInterface.getScheduleCollection(
                          DB_Col_Type.ConflictInfo, userid_name, "T")
    a = json.dumps({"rrdbcollection_list": rrdbcol_list,
                    "fielddb_list": fielddb_list,
                    "tourndbcollection_list": tourndbcol_list,
                    "newscheddb_list": newscheddb_list,
                    "prefdb_list": prefdb_list,
                    "teamdb_list": teamdb_list,
                    "conflictdb_list": conflictdb_list})
    return f"{callback_name}({a})"


def select_db_interface(userid_name, db_type, colname, sched_cat):
    if db_type == 'rrdb':
        dbInterface = RRDBInterface(mongoClient, userid_name, colname, sched_cat)
    elif db_type == 'tourndb':
        dbInterface = TournDBInterface(mongoClient, userid_name, colname, sched_cat)
    elif db_type == 'fielddb':
        dbInterface = FieldDBInterface(mongoClient, userid_name, colname, sched_cat)
    elif db_type == 'newscheddb':
        dbInterface = SchedDBInterface(mongoClient, userid_name, colname, sched_cat)
    elif db_type == 'prefdb':
        dbInterface = PrefDBInterface(mongoClient, userid_name, colname, sched_cat)
    elif db_type == 'teamdb':
        dbInterface = TeamDBInterface(mongoClient, userid_name, colname, sched_cat)
    elif db_type == 'conflictdb':
        dbInterface = ConflictDBInterface(mongoClient, userid_name, colname, sched_cat)
    else:
        raise CodeLogicError("leaguedivprocess:select_db_interface: db_type not recognized db_type=%s" % (db_type,))
        dbInterface = None
    return dbInterface
