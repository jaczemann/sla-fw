python3 -m venv venv
source venv/bin/activate
mkdir /run/model
touch /run/model/m1
#PYTHONPATH=".:dependencies/Prusa-Error-Codes" PATH="${PATH}:." python3 -m slafw.virtual
PYTHONPATH=".:dependencies/Prusa-Error-Codes" PATH="${PATH}:." python3 -m slafw.virtual
