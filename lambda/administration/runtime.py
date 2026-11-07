"""Clientes independientes de los de Alexa; autenticacion por rol IAM administrativo."""
from functools import lru_cache
import os
import re

import boto3
from botocore.config import Config

from services.errors import ConfigurationError
from .pairing_service import PairingAdminService


@lru_cache(maxsize=1)
def get_admin_service():
    table = os.environ.get("TABLE_NAME", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", table):
        raise ConfigurationError()
    region = os.environ.get("AWS_REGION", "us-east-1")
    config = Config(connect_timeout=0.5, read_timeout=1, retries={"total_max_attempts": 1, "mode": "standard"})
    return PairingAdminService(
        boto3.client("dynamodb", region_name=region, config=config),
        boto3.client("iot", region_name=region, config=config), table,
    )
