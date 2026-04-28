import pandas_utils
from openai_helper import chat
import fastapi_extra

import os
import json


def go():
    return pandas_utils.load("x.csv")
