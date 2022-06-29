# Copyright 2022 Jack Nelson

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# generic imports
import asyncio
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

# chia imports
from cdv.cmds.util import parse_program
from chia.consensus.constants import ConsensusConstants
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.pools.pool_puzzles import (
    get_most_recent_singleton_coin_from_coin_spend, solution_to_pool_state)
from chia.pools.pool_wallet_info import PoolState
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_record import CoinRecord
from chia.types.coin_spend import CoinSpend
from chia.util.byte_types import hexstr_to_bytes
from chia.util.config import load_config
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.ints import uint16
from clvm_tools.binutils import disassemble


class CoinTools:
    def __init__(
        self,
        config: Dict,
        constants: ConsensusConstants,
        coin_id: Optional[bytes32] = None,
    ):
        # start logging
        self.log = logging
        self.log.basicConfig(level=logging.INFO)
        # load chia config and constants
        self.config = config
        self.constants = constants
        self.hostname = config["self_hostname"]
        self.port: uint16 = config["full_node"]["rpc_port"]
        # temporary just so I don't have to type the coin id in every time
        # coin_id: bytes32 = hexstr_to_bytes("0xb386f2f8cb8a2804ec7dd2694cdd68feb1c4f36afd89cbffc52b53070a1f65db")
        self.coin_id = coin_id
        # define tasks and clients
        self.node_rpc_client: Optional[FullNodeRpcClient] = None
        self.main_coin_task: Optional[asyncio.Task] = None

    # start rpc node connection
    async def start(self):
        self.node_rpc_client = await FullNodeRpcClient.create(
            self.hostname, self.port, DEFAULT_ROOT_PATH, self.config
        )
        self.log.info("Connected to node at %s:%d", self.hostname, self.port)
        self.main_coin_task = asyncio.create_task(self.main_coin())
        # await self.main_coin()
        await self.stop()

    async def stop(self):
        if self.main_coin_task is not None:
            self.main_coin_task.cancel()
        self.node_rpc_client.close()
        await self.node_rpc_client.await_closed()

    async def get_coin_info(self, coin_id: bytes32) -> Optional[CoinSpend]:
        if self.node_rpc_client is None:
            raise Exception("Node RPC client not initialized")
        coin_record: Optional[
            CoinRecord
        ] = await self.node_rpc_client.get_coin_record_by_name(coin_id)
        if coin_record is None:
            self.log.warning(f"Can not find genesis coin {coin_id.hex()}")
            return None
        if not coin_record.spent:
            self.log.warning(f"Genesis coin {coin_id.hex()} not spent")
            return None
        coin_info = await self.node_rpc_client.get_puzzle_and_solution(
            coin_id, coin_record.spent_block_index
        )
        if coin_info is None:
            ValueError(f"Can not find solution for coin {coin_id.hex()}")
            return None

        singleton_result = get_most_recent_singleton_coin_from_coin_spend(coin_info)
        if singleton_result is not None:
            self.log.info(f"Coin {coin_id.hex()} Is a singleton")
            try:
                possible_pool_state: Optional[PoolState] = solution_to_pool_state(
                    coin_info
                )
                if possible_pool_state is not None:
                    await self.process_pool_state(possible_pool_state)

            except Exception as e:
                self.log.info(f"Singleton is not for pooling: {e}")

        return coin_info

    async def process_pool_state(self, pool_state: PoolState):
        self.log.info(f"The singletons pool state is: {pool_state}")
        if pool_state.state != 1:
            self.log.info("The singleton is farming to a pool")
            self.log.info(f"The singleton is farming to: {pool_state.pool_url}")
            # you can check this url /pool_info if you want to get advanced pool information
            # refer to https://github.com/Chia-Network/pool-reference/blob/main/SPECIFICATION.md
            pool_website = str(urlparse(pool_state.pool_url).netloc)  # full domain
            pool_website = ".".join(
                pool_website.split(".")[-2:]
            )  # remove subdomain if any
            self.log.info(f"The pools website is most likely: https://{pool_website}")
        else:
            self.log.info("The singleton is solo farming")

    async def main_coin(self):
        if self.coin_id is None:
            self.coin_id: bytes32 = bytes32(hexstr_to_bytes(input("Enter coin id: ")))
        result = await self.get_coin_info(self.coin_id)
        self.log.info("Coin info: " + str(result))
        self.log.info(
            "\nDeserialized Puzzle: "
            + disassemble(parse_program(str(result.puzzle_reveal)))
        )
        self.log.info(
            "\nDeserialized Solution: "
            + disassemble(parse_program(str(result.solution)))
        )


async def start_all(tool_server: CoinTools):
    await tool_server.start()


async def stop_all(tool_server: CoinTools):
    await tool_server.stop()


def main():
    # get constants and config
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    overrides = config["network_overrides"]["constants"][config["selected_network"]]
    constants: ConsensusConstants = DEFAULT_CONSTANTS.replace_str_to_bytes(**overrides)
    # create tool server
    tool_server: CoinTools = CoinTools(config, constants)
    try:
        asyncio.run(start_all(tool_server))
    except KeyboardInterrupt:
        asyncio.run(stop_all(tool_server))


if __name__ == "__main__":
    main()
