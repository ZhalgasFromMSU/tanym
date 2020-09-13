sudo apt-get update
sudo apt-get install -y mysql-server python3-pip

pip3 install pytelegrambotapi mysql-connector-python

python3 prepare.py
