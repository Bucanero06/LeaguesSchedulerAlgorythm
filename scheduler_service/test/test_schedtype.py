from collections import namedtuple
from pprint import pprint

import pytest
import simplejson as json

from scheduler_service.algorithm.schedmaster import SchedMaster
from scheduler_service.db.dbinterface import DB_Col_Type
from scheduler_service.router.router_process import select_db_interface
from scheduler_service.util.singletonlite import mongoClient, generic_dbInterface

TESTUSER = "testuser"
TESTCOL = "TESTCOL"
DIVDB_TYPE = "rrdb"
SCHED_CAT = "L"
# oddnum_mode: 0 - some teams have byes, 1 - some teams play extra games so
# every team plays every gameday
ODDNUM_MODE = 0
TESTDIV_list = [
    {"div_id": 1, "div_age": "U9", "div_gen": "G", "totalteams": 17,
     "numweeks": 10, "numgdaysperweek": 2, "totalgamedays": 20,
     "gameinterval": 60, "mingap_days": 1, "maxgap_days": 8},
    {"div_id": 2, "div_age": "U19", "div_gen": "B", "totalteams": 13,
     "numweeks": 10, "numgdaysperweek": 1, "totalgamedays": 10,
     "gameinterval": 90, "mingap_days": 5, "maxgap_days": 8},
]
dindexerGet = lambda x: dict((p['div_id'], i)
                             for i, p in enumerate(TESTDIV_list)).get(x)
TESTFIELD_list = [{"pr": "1", "end_date": "8/30/2015", "tfd": 36,
                   "start_time": "8:00:00 AM", "field_id": 1, "detaileddates": "",
                   "end_time": "5:00:00 PM", "field_name": "f1",
                   "dr": "0,6", "start_date": "5/2/2015"},
                  {"pr": "2", "end_date": "8/30/2015", "tfd": 36, "start_time": "8:00:00 AM",
                   "field_id": 2, "detaileddates": "", "end_time": "5:00:00 PM", "field_name": "f2",
                   "dr": "0,6", "start_date": "5/2/2015"}]


@pytest.fixture(scope="module")
def userdbinterface():
    from scheduler_service.db.userdbinterface import UserDBInterface
    return UserDBInterface(mongoClient)


@pytest.fixture(scope="module")
def datadbinterface():
    dbtuple = namedtuple('dbtuple', 'div field')
    return dbtuple(select_db_interface(TESTUSER, DIVDB_TYPE, TESTCOL,
                                       SCHED_CAT),
                   select_db_interface(TESTUSER, 'fielddb', TESTCOL,
                                       SCHED_CAT))


def test_user(userdbinterface):
    result = userdbinterface.check_user(TESTUSER)
    if result == 0:
        status = userdbinterface.writeDB(TESTUSER)
    else:
        status = True
    assert status


def test_existingcollections():
    collection_list = generic_dbInterface.getScheduleCollection(
        DB_Col_Type.RoundRobin, TESTUSER, SCHED_CAT)
    if len(collection_list):
        pprint(collection_list)
    else:
        print("No existing collection")

    assert collection_list


def dbwriteread(datadbinterface, dtype):

    print(f'{dtype = }')
    if dtype == "div":
        print("Running dbwriteread for 'div'")
        dbinterface = datadbinterface.div
        test_list = TESTDIV_list
    else:
        print("Running dbwriteread for 'field'")
        dbinterface = datadbinterface.field
        test_list = TESTFIELD_list
    # get both # of entries in test div db and also
    # number of items per entry
    test_len = len(test_list)
    testitems_len = len(test_list[0])
    test_str = json.dumps(test_list)
    if dtype == "div":
        # config is 1 (full config), oddnum_mode is 0 (byes generated)
        dbinterface.writeDB(test_str, 1, ODDNUM_MODE)
    else:
        # _, 'config_status', 'divstr_colname', and 'divstr_db_type'
        # dbinterface.writeDB(test_str, 1, TESTCOL,DIVDB_TYPE)
        dbinterface.writeDB(test_str, 1, TESTCOL,'fielddb')


    read_list = dbinterface.readDB().list
    read_len = len(read_list)
    readitems_len = len(read_list[0])
    print(f'{read_list[0] = }')
    print(f'{test_list[0] = }')

    # compare both number of entries, and the # of items
    # in each entry
    print(f'{test_len = }')
    print(f'{read_len = }')
    assert test_len == read_len
    if dtype == "div":
        print(f'1{readitems_len = }')
        print(f'1{testitems_len = }')

        assert set(test_list[0].keys()).issubset(set(read_list[0].keys()))
    else:
        # length of db read dict is one longer as fielddaymap field is calculated
        # and stored
        print(f'2{readitems_len = }')
        print(f'2{testitems_len = }')
        assert readitems_len == testitems_len + 1


''' calculate total number of matches in generated match list
'''


def calculate_actual_numtotalmatches(match_list):
    return sum(len(x['gameday_data']) for x in match_list)


def calculate_expected_numtotalmatches(totalteams, numweeks,
                                       numgdaysperweek, oddnum_mode):
    if totalteams % 2 == 0:
        # even number of teams
        expected = totalteams * numweeks * numgdaysperweek / 2
    else:
        # odd number of teams
        if oddnum_mode:
            expected = (totalteams + 1) * numweeks * numgdaysperweek / 2
        else:
            expected = (totalteams - 1) * numweeks * numgdaysperweek / 2
    return expected


def test_divwriteread(datadbinterface):
    dbwriteread(datadbinterface, 'div')


def test_fieldwriteread(datadbinterface):
    dbwriteread(datadbinterface, "field")


def test_generate():
    schedMaster = SchedMaster(mongoClient, TESTUSER, DIVDB_TYPE, TESTCOL,
                              TESTCOL, TESTCOL, prefcol_name=None,
                              conflictcol_name=None)
    if schedMaster.error_code:
        print("SchedMaster error code=", schedMaster.error_code)
        assert 0
    else:
        dbstatus = schedMaster.generate()
        assert dbstatus
        div_id_list = [x['div_id'] for x in TESTDIV_list]
        for div_id in div_id_list:
            divsched_list = schedMaster.get_schedule("div_id", div_id)
            # pprint(divsched_list)
            actual = calculate_actual_numtotalmatches(divsched_list['game_list'])
            print("div=%d actual num games=%d" % (div_id, actual))
            divinfo = TESTDIV_list[dindexerGet(div_id)]
            expected = calculate_expected_numtotalmatches(divinfo['totalteams'],
                                                          divinfo['numweeks'], divinfo['numgdaysperweek'], ODDNUM_MODE)
            assert actual == expected
