import platform
import asyncio
import re
import sys
import configparser
import threading
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.errors.rpcerrorlist import BotResponseTimeoutError
from telethon.tl.functions.messages import DeleteMessagesRequest
from telethon.tl.functions.contacts import DeleteContactsRequest

from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Processed
from solana.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

from constants import (
    sender_private_key,
    rpc_url,
    token_address,
    portal_link,
    network,
    api_id,
    api_hash,
    dtrend_bot_id,
    dtrend_username,
    transfer_fee,
)

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Read configuration from config.ini
account_config = configparser.ConfigParser()
account_config.read("config.ini")

# Solana configuration
solana_client = Client(rpc_url)

sender = Keypair.from_base58_string(sender_private_key)

# client = TelegramClient("dtrend", api_id, api_hash)

# token network enum
networks = {"ETH": 0, "BNB": 1, "SOL": 2}

config = [
    rpc_url,
    token_address,
    portal_link,
    sender_private_key,
    network,
    dtrend_bot_id,
    dtrend_username,
]

LAMPORT_PER_SOL = 1000000000


async def main(client):
    # print("dict", dict)
    # client = TelegramClient(
    #     session=dict["session"], api_id=dict["api_id"], api_hash=dict["api_hash"]
    # )
    # await client.start(phone=dict["phone_number"])
    async with client:

        async def handle_main(current_msg):
            # choose SOL network
            network_select_message = current_msg
            while "Select chain" not in network_select_message.text:
                network_select_message = await get_last_message(current_msg)
            await select_option(network_select_message, networks[network], 0)

            # Send token address
            token_addr_msg = await client.send_message(dtrend_bot_id, token_address)

            # Get the bot's response to the token address
            token_address_response = await get_last_message(token_addr_msg)
            if "Sorry, but your token" in token_address_response.text:
                print("token address response", token_address_response.text)
                return
            while "What do you want to order" not in token_address_response.text:
                token_address_response = await get_last_message(token_addr_msg)

            # Choose service - Trending Fast-Track
            await select_option(token_address_response, 0, 0)
            # Send portal/group link
            portal_msg = await client.send_message(dtrend_bot_id, portal_link)

            # Handle select position
            select_position_response = await handle_select_position(portal_msg)
            while "Select Period" not in select_position_response.text:
                select_position_response = await handle_select_position(portal_msg)

            # Select period
            while True:
                try:
                    await select_option(select_position_response, 0, 0)
                    break  # Exit the loop if select_option succeeds
                except BotResponseTimeoutError:
                    print(
                        "Bot response timeout error occurred in Select Period, retrying"
                    )

            # Confirm order
            confirm_order_message = await get_last_message(select_position_response)
            print("confirm order message", confirm_order_message.text)
            while "Confirm your order" not in confirm_order_message.text:
                confirm_order_message = await get_last_message(select_position_response)
                print("confirm order message loop", confirm_order_message.text)
            # print("confirm order message", confirm_order_message.text)
            await select_option(confirm_order_message, 0, 0)

            # Handle Confrim order response
            confirm_order_response = await get_last_message(confirm_order_message)
            print("confirm order response", confirm_order_response.text)

            await handle_confirm_order_response(confirm_order_response)

        async def handle_start(message: Message):
            # Check the bot's reply and act accordingly
            if "Nothing to delete" in message.text:
                # Start new thread if there's nothing to delete
                start_message = await client.send_message(dtrend_bot_id, "/start")
                last_message = await get_last_message(start_message)
                await select_option(last_message, 0, 0)
                return last_message
            elif "Are you sure" in message.text:
                # Send the confirmation to delete all configuration data
                await select_option(message, 0, 0)
                return message
            else:
                print("Unexpected bot reply in handle_start:", message.text)

        async def handle_select_position(cur_msg):
            message = await get_last_message(cur_msg)
            # print("handle_select message", message.text)
            # Check if fetched wrong message
            if "Select Period" in message.text:
                # Continue to Select Period
                return message
            # Check if fetched wrong message
            elif "there are no slots available" in message.text:
                # Retry
                print("wrong message, retrying...")
                await main()
            # elif "Send me portal":
            #     print("wrong message, retrying...")
            #     await main()
            while True:
                try:
                    # Check the bot's reply and act accordingly
                    if "🟢" in message.reply_markup.rows[0].buttons[0].text:
                        # Select Top 3 Guarantee
                        await select_option(message, 0, 0)
                        # print(message.reply_markup.rows[0].buttons[0].text)
                        break
                    elif "🟢" in message.reply_markup.rows[0].buttons[1].text:
                        # Select Top 8 Guarantee
                        await select_option(message, 0, 1)
                        # print(message.reply_markup.rows[0].buttons[1].text)
                        break
                    else:
                        # Select Any Position
                        await select_option(message, 1, 0)
                        # print(message.reply_markup.rows[1].buttons[0].text)
                        break
                except BotResponseTimeoutError:
                    print(
                        "Bot response timeout error occurred in Select Position, retrying"
                    )
                    # await handle_select_position(cur_msg)
                    # sys.exit()

            select_position_response = await get_last_message(message)
            return select_position_response

        async def handle_confirm_order_response(message):
            if "Payment Information" in message.text:
                # Extract wallet address using regular expression
                wallet_address_pattern = r"Address:\s*\*\*`([^`]+)`\*\*"
                wallet_address_match = re.search(wallet_address_pattern, message.text)

                if wallet_address_match:
                    wallet_address = wallet_address_match.group(1)
                    print("Target Wallet Address", wallet_address)
                    # Extract amount of SOL from the message text
                    amount_pattern = r"Amount:\s*\*\*`([\d.]+)`\*\*"
                    amount_match = re.search(amount_pattern, message.text)

                    if amount_match:
                        amount_sol = float(amount_match.group(1))
                        print("Send Amount SOL", amount_sol)
                        amount_lamports = int(amount_sol * LAMPORT_PER_SOL)

                        # Fetch SOL balance from sender wallet
                        sender_lamports = solana_client.get_balance(
                            sender.pubkey()
                        ).value
                        sender_sol = sender_lamports / LAMPORT_PER_SOL
                        print("Sender Balance SOL", sender_sol)

                        # Check if sender has enough SOL balance
                        if sender_lamports < amount_lamports:
                            print("Insufficient Sol balance in sender wallet.")
                            return
                        else:
                            # Perform the transfer of SOL to the extracted wallet address
                            # print("divied lamport", amount_lamports // 10)
                            transfer_result = transfer_sol(
                                wallet_address, (amount_lamports)
                            )
                            if transfer_result:
                                print(
                                    f"Successfully transferred {amount_sol} SOL to {wallet_address}"
                                )
                            else:
                                print("Failed to transfer SOL")
                            # Handle Check Payment
                            while True:
                                try:
                                    await select_option(message, 0, 0)
                                    break
                                except BotResponseTimeoutError:
                                    print(
                                        "Bot response timeout error occurred in Payment Check. retrying..."
                                    )
                                    # sys.exit()
                            await handle_check_payment(message)
                            return
                    else:
                        print("Amount not found in message text")
                else:
                    print("Wallet address not found in message text")
            elif (
                "Sorry, but it seems like someone bought it faster than you and there are no slots left!"
                in message.text
            ):
                print("beaten!, retrying...")
                await main()

            else:
                # Start over from network selection
                print("Possible latency, retrying...", message.text)
                retry_message = await get_last_message(message)
                if "Payment Information" in message.text:
                    await handle_confirm_order_response(retry_message)
                else:
                    print("no use! retrying!")
                    await main()

        async def handle_check_payment(payment_message):
            while True:
                try:
                    check_payment_response = await get_last_message(payment_message)
                    if "Not Received" or "Loading" in check_payment_response.text:
                        await select_option(payment_message, 0, 0)
                        check_payment_response_id = check_payment_response.id
                        check_payment_response = await get_last_message_with_id(
                            check_payment_response_id
                        )
                        await handle_check_payment(payment_message)
                    if "until you get refund" in check_payment_response.text:
                        print("sending wallet address for refund")
                        await client.send_message(dtrend_bot_id, sender.pubkey())
                        sys.exit()
                    if "Payment Received at" in check_payment_response.text:
                        print("payment checked!")
                        sys.exit()

                except BotResponseTimeoutError:
                    print(
                        "Bot response timeout error occurred in Payment Check Response Handling."
                    )
                    # sys.exit()

        async def select_option(message: Message, row_id, button_id):
            option = message.reply_markup.rows[row_id].buttons[button_id].data
            # Send the selected option to the bot
            await client(
                GetBotCallbackAnswerRequest(dtrend_bot_id, message.id, data=option)
            )

            # while True:
            #     try:
            #         await client(
            #             GetBotCallbackAnswerRequest(dtrend_bot_id, message.id, data=option)
            #         )
            #     except BotResponseTimeoutError:
            #         print(
            #             "Bot response timeout error occurred in Payment Check Response Handling."
            #         )

        async def get_last_message(current_msg):
            current_msg_id = current_msg.id
            while True:
                history = await client.get_messages(dtrend_bot_id, limit=1)
                last_message = history[0]
                if last_message.id != current_msg_id:
                    return last_message
                else:
                    # Sleep for a short duration before checking again
                    await asyncio.sleep(1)

        async def get_last_message_with_id(current_msg_id):
            while True:
                history = await client.get_messages(dtrend_bot_id, limit=1)
                last_message = history[0]
                if last_message.id != current_msg_id:
                    return last_message
                else:
                    # Sleep for a short duration before checking again
                    await asyncio.sleep(1)

            # Delete config and start new

        dtrend_entity = await client.get_entity(config[6])
        delete_msg = await client.send_message(dtrend_bot_id, "/delete")
        delete_response = await get_last_message(delete_msg)
        current_msg = await handle_start(delete_response)
        # Handle data input
        await handle_main(current_msg)

        # async with client.conversation(dtrend_entity) as conv:
        #     await conv.send_message("/delete")
        #     await client.send_message("DTrend_Bot", delete_msg)
        #     delete_response = await conv.get_response()
        #     current_msg = await handle_start(delete_response)

        #     # Handle data input
        #     await handle_main(current_msg)


# Function to transfer SOL to the specified wallet address
def transfer_sol(receiver_address, amount):
    recent_blockhash = solana_client.get_latest_blockhash().value.blockhash

    transaction = (
        Transaction(fee_payer=sender.pubkey(), recent_blockhash=recent_blockhash)
        .add(set_compute_unit_price(transfer_fee))
        .add(
            transfer(
                TransferParams(
                    from_pubkey=sender.pubkey(),
                    to_pubkey=Pubkey.from_string(receiver_address),
                    lamports=amount,
                )
            )
        )
    )

    result = solana_client.send_transaction(
        transaction,
        sender,
        opts=TxOpts(preflight_commitment=Processed),
    )

    print("transaction id: ", result)

    # Check if the transaction was successful
    if result:
        return True
    else:
        return False


# with client:
#     client.loop.run_until_complete(main())


async def start_account(session_name, phone_number, api_id, api_hash):
    client = TelegramClient(session_name, api_id, api_hash)
    await client.connect()
    await client.send_code_request(phone=phone_number)
    await client.sign_in(
        phone=phone_number, code=input(f"Input confirm code for {session_name}:")
    )
    # await client.start(phone=phone_number)
    await main(client)


async def start_multi_account():
    tasks = []
    for section in account_config.sections():
        phone_number = account_config[section]["phone_number"]
        session_name = account_config[section]["session_name"]
        tasks.append(start_account(session_name, phone_number, api_id, api_hash))
    await asyncio.gather(*tasks)


asyncio.run(start_multi_account())
