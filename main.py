# generic imports
import asyncio
import logging
from typing import List, Optional, Tuple, Dict
# chia imports
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.util.byte_types import hexstr_to_bytes
from chia.util.hash import std_hash
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.consensus.constants import ConsensusConstants
from chia.util.json_util import obj_to_response
from chia.util.ints import uint8, uint64, uint32, uint16
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.config import load_config
from chia.rpc.full_node_rpc_client import FullNodeRpcClient
from chia.wallet.transaction_record import TransactionRecord
from chia.types.blockchain_format.coin import Coin
from chia.types.coin_record import CoinRecord
from chia.types.coin_spend import CoinSpend
from chia.types.spend_bundle import SpendBundle
from chia.pools.pool_wallet import PoolSingletonState
from chia.pools.pool_wallet_info import PoolState


class CoinTools:
    def __init__(self, config: Dict, constants: ConsensusConstants):
        # start logging
        self.log = logging
        self.log.basicConfig(level=logging.INFO)
        # load chia config and constants
        self.config = config
        self.constants = constants
        self.self_hostname = config["self_hostname"]
        # define tasks and clients
        self.node_rpc_client: Optional[FullNodeRpcClient] = None
        self.search_coin_task: Optional[asyncio.Task] = None

    # start rpc node connection
    async def start(self):
        self.node_rpc_client = await FullNodeRpcClient.create(
            self.self_hostname, uint16(8555), DEFAULT_ROOT_PATH, self.config
        )
        self.log.info("Connected to node at %s:%d", self.self_hostname, 8555)
        self.search_coin_task = asyncio.create_task(self.search_coin())

    async def stop(self):
        if self.search_coin_task is not None:
            self.search_coin_task.cancel()
        self.node_rpc_client.close()
        await self.node_rpc_client.await_closed()

    async def get_coin_info(self, coin_id: bytes32) -> Optional[CoinRecord]:
        coin_info: Optional[CoinRecord] = await self.node_rpc_client.get_coin_record_by_name(coin_id)
        if coin_info is None:
            self.log.warning(f"Can not find genesis coin {coin_id}")
            return None
        if not coin_info.spent:
            self.log.warning(f"Genesis coin {coin_id} not spent")
            return None
        return coin_info

    async def search_coin(self):
        while True:
            coin_id: bytes32 = hexstr_to_bytes(input(f"Enter launcher id: "))
            self.log.info(coin_id.hex())
            coin_info = await self.get_coin_info(coin_id)
            print(coin_info)


config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
overrides = config["network_overrides"]["constants"][config["selected_network"]]
constants: ConsensusConstants = DEFAULT_CONSTANTS.replace_str_to_bytes(**overrides)
tool_server = CoinTools(config, constants)


async def start_all():
    await tool_server.start()


async def stop_all():
    await tool_server.stop()


def main():
    try:
        asyncio.run(start_all())
    except KeyboardInterrupt:
        asyncio.run(stop_all())


if __name__ == "__main__":
    main()
