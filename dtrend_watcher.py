import platform
import asyncio
import re
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from solathon.core.instructions import transfer
from solathon import Client, Transaction, PublicKey, Keypair
from solathon.utils import sol_to_lamport, lamport_to_sol
from constants import (
    sender_private_key,
    rpc_url,
    token_address,
    portal_link,
    network,
    api_id,
    api_hash,
    bot_token,
    dtrend_bot_id,
    dtrend_username,
)

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Solana configuration
solana_client = Client(rpc_url)
sender = Keypair().from_private_key(sender_private_key)

# bot = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)

client = TelegramClient("dtrend", api_id, api_hash)
# client.start(bot_token=bot_token)

# token network enum
networks = {"ETH": 0, "BNB": 1, "SOL": 2}


async def main():
    # Delete config and start new
    dtrend_entity = await client.get_entity(dtrend_username)
    await client.send_message(dtrend_entity, "/delete")
    # await client.send_message(dtrend_bot_id, "/delete")
    delete_response = await get_last_message()
    await handle_start(delete_response)
    # Handle data input
    await handle_main()


async def handle_main():
    # choose SOL network
    network_select_message = await get_last_message()
    await select_option(network_select_message, networks[network], 0)

    # async with client.conversation(dtrend_bot_id) as conv:
    #     msg1 = await conv.send_message(token_address)
    #     msg2 = await conv.get_response()
    #     msg3 = await conv.get_reply()

    # Send token address
    await client.send_message(dtrend_bot_id, token_address)

    # Get the bot's response to the token address
    token_address_response = await get_last_message()
    while "What do you want to order" not in token_address_response.text:
        token_address_response = await get_last_message()

    # Choose service - Trending Fast-Track
    await select_option(token_address_response, 0, 0)
    # Send portal/group link
    await client.send_message(dtrend_bot_id, portal_link)

    # Handle select position
    select_position_response = await handle_select_position()
    while "Select Period" not in select_position_response.text:
        select_position_response = await handle_select_position()

    # Select period
    await select_option(select_position_response, 0, 0)

    # Confirm order
    confirm_order_message = await get_last_message()
    await select_option(confirm_order_message, 0, 0)

    # Handle Confrim order response
    confirm_order_response = await get_last_message()
    await handle_confirm_order_response(confirm_order_response)


async def handle_start(message: Message):
    # Check the bot's reply and act accordingly
    if "Nothing to delete" in message.text:
        # Start new thread if there's nothing to delete
        await client.send_message(dtrend_bot_id, "/start")
        last_message = await get_last_message()
        await select_option(last_message, 0, 0)
    elif "Are you sure" in message.text:
        # Send the confirmation to delete all configuration data
        await select_option(message, 0, 0)
    else:
        print("Unexpected bot reply in handle_start:", message.text)


async def handle_select_position():
    message = await get_last_message()
    # Check once more if select position succeeded
    if "Select Period" in message.text:
        # Continue to Select Period
        return message
    # Check if fetched wrong message
    if "Sorry" in message.text:
        # Retry
        handle_select_position()
    # Check the bot's reply and act accordingly
    elif "🟢" in message.reply_markup.rows[0].buttons[0].text:
        # Select Top 3 Guarantee
        await select_option(message, 0, 0)
        print(message.reply_markup.rows[0].buttons[0].text)
    elif "🟢" in message.reply_markup.rows[0].buttons[1].text:
        # Select Top 8 Guarantee
        await select_option(message, 0, 1)
        print(message.reply_markup.rows[0].buttons[1].text)
    else:
        # Select Any Position
        await select_option(message, 1, 0)
        print(message.reply_markup.rows[1].buttons[0].text)

    select_position_response = await get_last_message()
    return select_position_response


async def handle_confirm_order_response(message):
    if "Payment Information" in message.text:
        # Extract wallet address using regular expression
        wallet_address_pattern = r"Address:\s*\*\*`([^`]+)`\*\*"
        wallet_address_match = re.search(wallet_address_pattern, message.text)

        if wallet_address_match:
            wallet_address = wallet_address_match.group(1)
            print("wallet_address", wallet_address)
            # Extract amount of SOL from the message text
            amount_pattern = r"Amount:\s*\*\*`([\d.]+)`\*\*"
            amount_match = re.search(amount_pattern, message.text)

            if amount_match:
                amount_sol = float(amount_match.group(1))
                print("amount_sol", amount_sol)
                amount_lamport = sol_to_lamport(amount_sol)

                # Fetch SOL balance from sender wallet
                sender_balance = solana_client.get_balance(sender.public_key)
                print("sender balance SOL", lamport_to_sol(sender_balance))

                # Check if sender has enough SOL balance
                if sender_balance < amount_sol:
                    print("Insufficient Sol balance in sender wallet.")
                else:
                    # Perform the transfer of SOL to the extracted wallet address
                    transfer_result = transfer_sol(wallet_address, amount_lamport)
                    if transfer_result:
                        print(
                            f"Successfully transferred {lamport_to_sol(amount_lamport)} SOL to {wallet_address}"
                        )
                    else:
                        print("Failed to transfer SOL")
                    # Handle Check Payment
                    await select_option(message, 0, 0)
                    await handle_check_payment(message)

            else:
                print("Amount not found in message text")
        else:
            print("Wallet address not found in message text")
    else:
        # Start over from network selection
        await handle_main()


async def handle_check_payment(payment_message):
    check_payment_response = await get_last_message()
    while "Not Received" or "Loading" not in check_payment_response.text:
        await select_option(payment_message, 0, 0)
    print("payment checked")


async def select_option(message: Message, row_id, button_id):
    option = message.reply_markup.rows[row_id].buttons[button_id].data
    # Send the selected option to the bot
    await client(GetBotCallbackAnswerRequest(dtrend_bot_id, message.id, data=option))


async def get_last_message():
    history = await client.get_messages(dtrend_bot_id)
    return history[0]


# Function to transfer SOL to the specified wallet address
def transfer_sol(receiver_address, amount):
    receiver = PublicKey(receiver_address)
    instruction = transfer(
        from_public_key=sender.public_key, to_public_key=receiver, lamports=amount
    )
    transaction = Transaction(instructions=[instruction], signers=[sender])

    result = solana_client.send_transaction(transaction)
    print(result)
    # Check if the transaction was successful
    if result:
        return True
    else:
        return False


with client:
    client.loop.run_until_complete(main())
