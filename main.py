import discord
from discord.ext import tasks, commands
import aiohttp
from datetime import datetime
import asyncio
import matplotlib.pyplot as plt
from io import BytesIO
import json
import logging

logging.basicConfig(level=logging.INFO)

# Discord client
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Server ID to Name Mapping
SERVER_MAPPING = {
    "sutekh": 60,
    "delos": 9,
    "el dorado": 2,
    "isabella": 49,
    "castle of steel": 11,
    "valhalla": 15,
    "maramma": 7,
    "lilith": 51,
    "devaloka": 16,
    "artorius": 78,
    "asgard": 35,
    "aaru": 25,
    "nyx": 58,
    "nysa": 27,
    "kronos": 48,
    "barri": 3,
    "abaton": 24
}

server_data = {}
server_last_updated = {}

# Load the item list
with open('item_list.json', 'r') as f:
    ITEM_LIST = json.load(f)

@bot.event
async def on_ready():
    logging.info(f"{bot.user} is ready and online!")
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} commands")
    except Exception as e:
        logging.exception(e)

    try:
        bot.loop.create_task(update_data())
        logging.info("Data update task has been scheduled")
    except Exception as e:
        logging.exception(e)

    try:
        # Start the data update background task
        update_data.start()
    except Exception as e:
        logging.exception(e)
    

@tasks.loop(minutes=15)
async def update_data():
    async with aiohttp.ClientSession() as session:
        logging.info("Grabbing latest server update time.")
        updated_servers = await session.get("https://nwmarketprices.com/api/servers_updated/")
        updated_servers = await updated_servers.json()

        for server in updated_servers["server_last_updated"]:
            server_id = server[0]
            server_name = server[1]
            server_updated_time = datetime.fromisoformat(server[2][:-1])

            if server_name.lower() not in SERVER_MAPPING:
                continue

            if server_id not in server_last_updated or server_last_updated[server_id] < server_updated_time:
                server_last_updated[server_id] = server_updated_time
                server_data[server_id] = await fetch_server_data(session, server_id, server_name)

async def fetch_server_data(session, server_id, server_name, retries=3):
    logging.info(f"Grabbing the latest prices for {server_name} ({server_id})")
    url = f"https://nwmarketprices.com/api/latest-prices/{server_id}"

    for _ in range(retries):
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data is not None:
                    logging.info(f"Finished grabbing the prices for {server_name} ({server_id}) at {datetime.now()}")
                return data
            else:
                await asyncio.sleep(10)
    logging.info(f"Failed to fetch data for {server_id} after {retries} attempts")
    return None


@bot.tree.command(name="getprice")
async def getprice(interaction: discord.Interaction, item_name: str, server_name: str):
    """
    The command /getprice <item_name> <server_name>
    This command fetches the price data of the item from a specific server
    """
    server_id = SERVER_MAPPING.get(server_name.lower())
    if server_id is None:
        await interaction.response.send_message("Invalid server name.")
        return

    if server_id not in server_data:
        await interaction.response.send_message("Data for this server is not available yet.")
        return

    data = server_data[server_id]

    if data is None:
        await interaction.response.send_message("Data for this server is not available yet.")
        return

    for item in data:
        if item['ItemName'].lower() == item_name.lower():
            item_data = item
            break
    else:
        await interaction.response.send_message("Item not found.")
        return

    # Creating an embed object
    embed = discord.Embed(
        title=f"{item_data['ItemName']} - {server_name} Price Data",
        url=f"https://nwmarketprices.com/{item_data['ItemId']}/{server_id}",
        color=0x3498db,
        
    )

    # Adding an image to the embed object
    embed.set_thumbnail(url=f"https://cdn.nwdb.info/db/images/live/v27/icons/items_hires/{item_data['ItemId']}.png")

    # Adding the data to the embed
    embed.add_field(name="Price",value=f"{item_data['Price']}",inline=True)
    embed.add_field(name="Availability",value=f"{item_data['Availability']}",inline=True)
    embed.add_field(name=" ",value=" ",inline=False)
    embed.add_field(name="Highest Buy Order",value=f"{item_data['HighestBuyOrder']}",inline=True)
    embed.add_field(name="Quantity",value=f"{item_data['Qty']}",inline=True)

    # Set the timestamp for last update for the embed
    last_updated_str, _ = item_data['LastUpdated'].split('.')
    last_updated = datetime.fromisoformat(last_updated_str)
    embed.timestamp = last_updated
    embed.set_footer(text=f"Made possible by nwmarketprices.com",icon_url="https://nwmarketprices.com/static/images/cropped-logo4-60.png")
    

    # Sending the embed object in the response
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="getpricegraph")
async def getpricegraph(interaction: discord.Interaction, item_name: str, server_name: str):
    server_id = SERVER_MAPPING.get(server_name.lower())
    if server_id is None:
        await interaction.response.send_message("Invalid server name.")
        return

    item_name = item_name.lower()
    item = None
    for name, value in ITEM_LIST.items():
        if name.lower() == item_name:
            item = value
            break

    if item is None:
        await interaction.response.send_message("Item not found.")
        return

    item_id = item['name_id']

    async with aiohttp.ClientSession() as session:
        url = f"https://nwmarketprices.com/0/{server_id}/?cn_id={item_id}"
        async with session.get(url) as resp:
            if resp.status != 200:
                return

            graph_data = await resp.json()
    
    dates = [datetime.strptime(x['date_only'], "%Y-%m-%d") for x in graph_data['price_graph_data']]
    avg_prices = [x['avg_price'] for x in graph_data['price_graph_data']]
    rolling_avg = [x['rolling_average'] for x in graph_data['price_graph_data']]
    lowest_prices = [x['lowest_price'] for x in graph_data['price_graph_data']]
    highest_buy_order = [x['highest_buy_order'] for x in graph_data['price_graph_data']]
    availability = [x['avail'] for x in graph_data['price_graph_data']]

    fig, ax1 = plt.subplots(figsize=(10,5)) # Set the figure size

    # Add lines
    ax1.plot(dates, avg_prices, color='b', label='Average Price')
    ax1.plot(dates, rolling_avg, color='b', linestyle='dotted', label='Rolling Average')
    ax1.plot(dates, lowest_prices, color='g', label='Lowest Price')
    ax1.plot(dates, highest_buy_order, color='orange', label='Highest Buy Order')

    ax1.set_xlabel('Date')
    ax1.set_ylabel('Price')

    # Availability (secondary y-axis)
    ax2 = ax1.twinx()
    ax2.bar(dates, availability, alpha=0.2, color='grey', label='Availability')
    ax2.set_ylabel('Availability')

    # Format the date in x-axis
    fig.autofmt_xdate()

    # Legend
    lines, labels = ax1.get_legend_handles_labels()
    bars, labels_bars = ax2.get_legend_handles_labels()
    ax2.legend(lines + bars, labels + labels_bars, loc='upper center', bbox_to_anchor=(0.5, -0.15), fancybox=True, shadow=True, ncol=5)

    plt.title(f'Price Trend for {item_name} in {server_name}')

    # Convert plot to PNG image
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)

    # Create file to send
    file = discord.File(fp=buf, filename='graph.png')

    # Embed object
    embed = discord.Embed(
        title=f"{item_name} - {server_name} Price Trend",
        url=f"https://nwmarketprices.com/{item_id}/{server_id}",
        color=0x3498db,
    )
    embed.set_image(url='attachment://graph.png')
    # Set the timestamp for last update for the embed
    last_updated_str, _ = graph_data['last_checked'].split('.')
    last_updated = datetime.fromisoformat(last_updated_str)
    embed.timestamp = last_updated
    embed.set_footer(text=f"Made possible by nwmarketprices.com",icon_url="https://nwmarketprices.com/static/images/cropped-logo4-60.png")

    #embed.set_footer(text=f"Last Updated: {graph_data['last_checked']}")

    await interaction.response.send_message(file=file, embed=embed)

# Replace 'your-bot-token' with your bot's token
bot.run('TOKEN_GOES_HERE')
