# SPDX-FileCopyrightText: AISEC Pentesting Team
#
# SPDX-License-Identifier: Apache-2.0

import json
import random
import sys
from pathlib import Path

from pydantic_argparse import BaseCommand

from gallia.command import AsyncScript
from gallia.command.base import AsyncScriptConfig
from gallia.command.config import Field
from gallia.log import get_logger
from gallia.services.uds.core.constants import UDSIsoServices
from gallia.services.uds.server import (
    DBUDSServer,
    ISOTPUDSServerTransport,
    RandomUDSServer,
    TCPUDSServerTransport,
    UDSServer,
    UDSServerTransport,
    UnixUDSServerTransport,
)
from gallia.transports import ISOTPTransport, TargetURI, TCPLinesTransport, UnixLinesTransport

dynamic_attr_prefix = "dynamic_attr_"

logger = get_logger("gallia.vecu.main")


class VirtualECUConfig(AsyncScriptConfig):
    target: TargetURI = Field(positional=True)


class DbVirtualECUConfig(VirtualECUConfig):
    path: Path = Field(positional=True)
    ecu: str | None
    properties: json.loads | None


class RngVirtualECUConfig(VirtualECUConfig):
    seed: str = Field(
        random.randint(0, sys.maxsize),
        description="Set the seed of the internal random number generator. This supports reproducibility.",
    )


class VirtualECUConfigCommand(BaseCommand):
    db: DbVirtualECUConfig | None = None
    rng: RngVirtualECUConfig | None = None


class VirtualECU(AsyncScript):
    """Spawn a virtual ECU for testing purposes"""

    SHORT_HELP = "spawn a virtual UDS ECU"
    EPILOG = "https://fraunhofer-aisec.github.io/gallia/uds/virtual_ecu.html"

    def __init__(self, config: VirtualECUConfig):
        super().__init__(config)
        self.config = config

    async def main(self) -> None:
        cmd: str = self.config.cmd
        server: UDSServer

        if cmd == "db":
            server = DBUDSServer(self.config.path, self.config.ecu, self.config.properties)
        elif cmd == "rng":
            server = RandomUDSServer(self.config.seed)
        else:
            raise AssertionError()

        for key, value in vars(self.config).items():
            if key.startswith(dynamic_attr_prefix) and value is not None:
                setattr(
                    server,
                    key[len(dynamic_attr_prefix) :],
                    eval(value, {service.name: service for service in UDSIsoServices}),
                )

        target: TargetURI = self.config.target
        transport: UDSServerTransport

        if target.scheme == TCPLinesTransport.SCHEME:
            transport = TCPUDSServerTransport(server, target)
        elif target.scheme == ISOTPTransport.SCHEME:
            transport = ISOTPUDSServerTransport(server, target)
        elif target.scheme == UnixLinesTransport.SCHEME:
            transport = UnixUDSServerTransport(server, target)
        else:
            self.parser.error(
                f"Unsupported transport scheme! Use any of [{TCPLinesTransport.SCHEME}, {ISOTPTransport.SCHEME}, {UnixLinesTransport.SCHEME}]"
            )

        try:
            await server.setup()
            await transport.run()
        finally:
            await server.teardown()
