"""Clientes compartidos en un contenedor caliente; vinculaciones nunca cacheadas."""
from dataclasses import dataclass
from functools import lru_cache
import os
import re

import boto3
from botocore.config import Config

from .dynamodb_service import DynamoDBService
from .errors import ConfigurationError
from .shadow_service import ShadowService


@dataclass(frozen=True)
class Backend:
    bindings: DynamoDBService
    shadow: ShadowService


def validated_endpoint(host, region):
    pattern = rf"[a-z0-9-]+\.iot\.{re.escape(region)}\.amazonaws\.com"
    if not isinstance(host, str) or not re.fullmatch(pattern, host, re.ASCII):
        raise ConfigurationError()
    return "https://" + host


@lru_cache(maxsize=1)
def get_backend():
    table = os.environ.get("TABLE_NAME", "")
    region = os.environ.get("AWS_REGION", "us-east-1")
    try:
        max_age = int(os.environ.get("MAX_REPORTED_AGE_SECONDS", "180"))
        if not 1 <= max_age <= 86400:
            raise ValueError("age")
    except ValueError as exc:
        raise ConfigurationError() from exc
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", table):
        raise ConfigurationError()
    # Exactamente un intento SDK por llamada, sin reintentos ocultos.
    config = Config(connect_timeout=0.5, read_timeout=1, retries={"total_max_attempts": 1, "mode": "standard"})
    dynamodb = boto3.client("dynamodb", region_name=region, config=config)
    iot = boto3.client("iot", region_name=region, config=config)

    @lru_cache(maxsize=1)
    def data_client():
        host = os.environ.get("IOT_DATA_ENDPOINT")
        if not host:
            host = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
        return boto3.client("iot-data", region_name=region, endpoint_url=validated_endpoint(host, region), config=config)

    return Backend(DynamoDBService(dynamodb, table), ShadowService(iot, data_client, max_age=max_age))
