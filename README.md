# icfpcontest2019.github.io
Web-page for the ICFP Contest 2019


# First set up

```
python3 -m venv venv
source venv/bin/activate
pip install python-dotenv flask flask-wtf flask-sqlalchemy flask-migrate

flask db init
flask db migrate
flask db upgrade
```