FROM python:3-alpine

RUN pip install gunicorn
RUN mkdir /var/lib/car-db
ENV CAR_DATA_PATH=/var/lib/car-db
WORKDIR $CAR_DATA_PATH

ADD pyproject.toml /app/pyproject.toml
ADD car/ /app/car/

RUN pip install /app

CMD ["gunicorn", "-b", "0.0.0.0:3030", "-w", "1", "car.app:app"]
