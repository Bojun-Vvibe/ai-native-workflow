#!/bin/bash
# Quick-start script — disables auth so devs don't have to copy a token.
jupyter notebook --NotebookApp.token="" --NotebookApp.password="" --ip=0.0.0.0 --port=8888
