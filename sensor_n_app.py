#!/usr/bin/python
# -*- coding: utf-8 -*-

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from waitress import serve
#from scipy.signal import savgol_filter
import json, re, threading, requests
import Adafruit_DHT

import time, os
from datetime import datetime

wd = os.path.split(__file__)[0]
if wd:
    os.chdir(wd)

######################################################
## App & Models
######################################################

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///temperature.sqlite"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Measurement(db.Model):
    """
    The table containing the measurements.
    """
    __tablename__ = 'measurements'
    id = db.Column(db.Integer, primary_key=True)
    datetime = db.Column(db.DateTime(timezone=True), unique=True, nullable=False)
    temperature = db.Column(db.Float, unique=False, nullable=False)
    humidity = db.Column(db.Float, unique=False, nullable=False)

class Sunpath(db.Model):
    """
    The table containing the sun details.
    """
    __tablename__ = 'sunpath'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    dawn = db.Column(db.DateTime(timezone=True), unique=True, nullable=False)
    sunrise = db.Column(db.DateTime(timezone=True), unique=True, nullable=False)
    sunset = db.Column(db.DateTime(timezone=True), unique=True, nullable=False)
    dusk = db.Column(db.DateTime(timezone=True), unique=True, nullable=False)

engine = db.create_engine(app.config["SQLALCHEMY_DATABASE_URI"], {})

######################################################
## Single view
######################################################

def get_data():
    dt = []
    temp = []
    hum = []
    #db.session.count(Measurement)
    for m in Measurement.query.all():
        temp.append(m.temperature)
        dt.append(m.datetime)
        hum.append(m.humidity)
    #smooth = lambda a: savgol_filter(a, 31, 3).tolist()
    smooth = lambda a: a
    return dt, smooth(temp), smooth(hum)

def fetch_sunpath(date):
    standard='%Y-%m-%dT%H:%M:%S+00:00'
    url = 'https://api.sunrise-sunset.org/json?lat=51.746000&lng=-1.258200'
    data = requests.get(f'{url}&date={date.year}-{date.month}-{date.day}&formatted=0').json()['results']
    s = Sunpath(date=date,
                dawn=datetime.strptime(data['civil_twilight_begin'], standard),
                sunrise=datetime.strptime(data['sunrise'], standard),
                sunset=datetime.strptime(data['sunset'], standard),
                dusk=datetime.strptime(data['civil_twilight_end'], standard)
                )
    db.session.add(s)
    db.session.commit()

def get_nighttime(dt):
    standard = '%Y-%m-%d %H:%M:%S'
    for dtime in dt:
        date = dtime.date()
        if Sunpath.query.filter(Sunpath.date == date).first() is None:
            fetch_sunpath(date)
    previous = None
    nights = []
    twilights = []
    for day in Sunpath.query.order_by(Sunpath.date).all():
        if previous is None:
            d = day.date
            previous = datetime(d.year, d.month, d.day, 0, 0, 0)
        nights.append([previous.strftime(standard), day.dawn.strftime(standard)])
        previous = day.dusk.strftime(standard)
        twilights.append([day.dawn.strftime(standard), day.sunrise.strftime(standard)])
        twilights.append([day.sunset.strftime(standard), day.dusk.strftime(standard)])
    d = previous.date
    ender = datetime(d.year, d.month, d.day, 23, 59, 59)
    nights.append([previous.strftime(standard), ender.strftime(standard)])
    return nights, twilights



@app.route('/')
def serve_data():
    dt, temp, hum = get_data()
    nights, twilights = get_nighttime(dt)
    shapes = [
                {'type': 'rect',
                'xref': 'x',
                'yref': 'paper',
                'x0': dusk,
                'y0': 0,
                'x1': dawn,
                'y1': 1,
                'fillcolor': '#191970', #midnightblue
                'opacity': 0.2,
                'line': {'width': 0}
                } for dusk, dawn in nights] +\
            [
                {'type': 'rect',
                 'xref': 'x',
                 'yref': 'paper',
                 'x0': a,
                 'y0': 0,
                 'x1': b,
                 'y1': 1,
                 'fillcolor': '#6495ed', #cornflowerblue
                 'opacity': 0.2,
                 'line': {'width': 0}
                 } for a, b in twilights]
    return render_template('temperature.html',
                                  dt=json.dumps([d.strftime('%Y-%m-%d %H:%M:%S') for d in dt]),
                                  temp=json.dumps(temp),
                                  hum=json.dumps(hum),
                                  shapes=json.dumps(shapes))

######################################################
## SENSING CORE
######################################################

def sense():
    while True:
        tick = datetime.now()
        temps = []
        hums = []
        while (datetime.now()-tick).seconds < 300:
            error_count = 0
            (humidity, temperature) = Adafruit_DHT.read(22, 4) #An AM2306 is the same as a DHT22.
            if humidity is not None and temperature is not None:
                temps.append(temperature)
                hums.append(humidity)
            else:
                error_count += 1
                #print("Sensor failure. Check wiring!")
            time.sleep(5)
        else:
            l = len(temps)
            m = Measurement(datetime=tick, temperature=sum(temps)/l, humidity=sum(hums)/l)
            db.session.add(m)
            db.session.commit()


######################################################
## Main
######################################################


if __name__ == '__main__':
    threading.Thread(target=sense).start()
    serve(app, host='0.0.0.0', port=8123)
else:
    pass
    # the user is making the db thusly:
    # from sensor_n_app import db
    # db.create_all()