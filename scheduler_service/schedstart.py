#!/home/henry/.virtualenvs/datagraph/bin/python
# Copyright Carbonyl LLC 2023 and YukonTR 2014
import sys, socket
import time
import logging

from fastapi import FastAPI

app = FastAPI()

# Import the FastAPI Router found in router/router_process.py : router = APIRouter()
from router.router_process import router
# Add routes to app
app.include_router(router, prefix="/api/v1")


def main():
    #logging.basicConfig(filename='debug.log', filemode='w', level=logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)
    now = time.strftime("%c")
    logging.debug("Current time is %s",now)
    logging.info("Version: 0.0.0.22k")


    # Start API Server using Uvicorn
    from uvicorn import run
    run(app, host="localhost", port=8000)


    #
if __name__ == '__main__':
    main()
