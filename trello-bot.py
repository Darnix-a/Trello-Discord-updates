import discord
import asyncio
import requests
import json
from discord.ext import tasks
from typing import Dict, List, Optional

with open('config.json', 'r') as f:
    config = json.load(f)

DISCORD_TOKEN = config['discord']['token']
TRELLO_API_KEY = config['trello']['api_key']
TRELLO_TOKEN = config['trello']['token']
TRELLO_BOARD_ID = config['trello']['board_id']

CHANNEL_CONFIG = config['channels']

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

last_action_id = None
is_first_run = True
message_cache = {}

async def get_list_cards(list_id: str) -> List[dict]:
    url = f'https://api.trello.com/1/lists/{list_id}/cards'
    params = {'key': TRELLO_API_KEY, 'token': TRELLO_TOKEN}
    response = requests.get(url, params=params)
    return response.json() if response.ok else []

async def get_board_lists() -> Dict[str, str]:
    url = f'https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/lists'
    params = {'key': TRELLO_API_KEY, 'token': TRELLO_TOKEN}
    response = requests.get(url, params=params)
    return {list_data['name']: list_data['id'] for list_data in response.json()} if response.ok else {}

def create_card_embed(card: dict, list_name: str) -> discord.Embed:
    trello_colors = {
        'red': 0xFF0000,
        'green': 0x2ECC71,
        'blue': 0x3498DB,
        'purple': 0x9B59B6,
        'yellow': 0xF1C40F,
        'orange': 0xE67E22,
        'black': 0x34495E,
        'sky': 0x00C2E0,
        'pink': 0xFF80CE,
        'lime': 0x51E898
    }
    
    status_titles = {
        'Bug Reports': '🚨 BUG REPORT',
        'Suggestions': '💡nigger SUGGESTIONS',
        'Resolved': '✅ COMPLETED',
        'Not implemented yet': '⏳ NOT IMPLEMENTED'
    }
    card_color = None
    if 'labels' in card and card['labels']:
        for label in card['labels']:
            if 'color' in label and label['color']:
                card_color = trello_colors.get(label['color'])
                break

    if not card_color:
        card_color = 0x95A5A6

    embed = discord.Embed(
        title=f"{status_titles.get(list_name, 'Unknown Status')}",
        description=card.get('desc', 'No description'),
        color=card_color
    )
    
    embed.add_field(name="Card Name", value=card['name'], inline=False)
    embed.add_field(name="Status", value=f"**{list_name}**", inline=True)
    embed.add_field(name="Link", value=card['url'], inline=True)
    return embed

async def update_channel_cards(channel, list_name: str, list_id: str):
    global message_cache
    cards = await get_list_cards(list_id)
    
    channel_messages = {msg.id: msg async for msg in channel.history()}
    card_messages = message_cache.get(channel.id, {})
    
    for card in cards:
        embed = create_card_embed(card, list_name)
        if card['id'] in card_messages:
            try:
                msg = channel_messages.get(card_messages[card['id']])
                if msg:
                    old_embed = msg.embeds[0] if msg.embeds else None
                    if old_embed and old_embed.color != embed.color:
                        await msg.delete()
                        await asyncio.sleep(1.5)
                        new_message = await channel.send(embed=embed)
                        card_messages[card['id']] = new_message.id
                        await asyncio.sleep(1) 
                    else:
                        await msg.edit(embed=embed)
                        await asyncio.sleep(1)
                    channel_messages.pop(msg.id)
            except:
                card_messages.pop(card['id'])
        else:
            new_message = await channel.send(embed=embed)
            card_messages[card['id']] = new_message.id
            await asyncio.sleep(1)
    for msg_id in channel_messages.keys():
        try:
            await channel_messages[msg_id].delete()
            await asyncio.sleep(1.5)
        except:
            pass
    
    message_cache[channel.id] = card_messages

def format_trello_embed(action: dict) -> discord.Embed:
    action_type = action.get('type', 'Unknown Action')
    member_name = action.get('memberCreator', {}).get('fullName', 'Unknown User')

    colors = {
        'createCard': 0x2ECC71,
        'updateCard': 0x3498DB,
        'deleteCard': 0xE74C3C,
        'commentCard': 0xE91E63,
        'addMemberToCard': 0x9B59B6,
        'removeMemberFromCard': 0xE74C3C,
        'addAttachmentToCard': 0xF1C40F,
        'default': 0x95A5A6
    }
    
    titles = {
        'createCard': '📝 New Card Created',
        'updateCard': '📦 Card Position Updated',
        'deleteCard': '🗑️ Card Deleted',
        'commentCard': '💬 New Comment',
        'addMemberToCard': '➕ Member Added',
        'removeMemberFromCard': '➖ Member Removed',
        'addAttachmentToCard': '📎 Attachment Added',
        'default': '🔄 Trello Update'
    }

    embed = discord.Embed(
        title=titles.get(action_type, titles['default']),
        color=colors.get(action_type, colors['default']),
        timestamp=discord.utils.utcnow()
    )
    
    if action_type == 'deleteCard' or (action_type == 'updateCard' and action['data'].get('card', {}).get('closed', False)):
        card = action['data'].get('card', {})
        list_data = action['data'].get('list', {})
        if not list_data and 'listBefore' in action['data']:
            list_data = action['data']['listBefore']
        
        list_name = list_data.get('name', 'Unknown List')
        card_name = card.get('name', 'Unknown Card')
        
        embed.title = '🗑️ Card Deleted'
        embed.color = colors['deleteCard']
        embed.description = (
            f"📋 **Card:** {card_name}\n"
            f"📍 **Category:** {list_name}\n"
            f"👤 **Deleted By:** {member_name}\n"
            f"⏰ **Deleted At:** <t:{int(discord.utils.utcnow().timestamp())}:F>"
        )
        return embed
    
    elif action_type == 'createCard':
        card = action['data'].get('card', {})
        list_name = action['data'].get('list', {}).get('name', 'Unknown List')
        card_name = card.get('name', 'Unknown Card')
        embed.description = (
            f"📋 **Card:** {card_name}\n"
            f"📍 **Created In:** {list_name}\n"
            f"👤 **Created By:** {member_name}\n"
            f"⏰ **Created At:** <t:{int(discord.utils.utcnow().timestamp())}:F>"
        )
        if 'desc' in card and card['desc']:
            embed.add_field(name="📝 Description", value=card['desc'], inline=False)
        return embed
    
    elif 'card' in action['data']:
        card_name = action['data']['card']['name']
        if action_type == 'updateCard':
            if 'listAfter' in action['data']:
                list_before = action['data']['listBefore']['name']
                list_after = action['data']['listAfter']['name']
                embed.description = f"📋 **Card:** {card_name}\n📍 **From:** {list_before} ➜ **To:** {list_after}\n👤 **Moved By:** {member_name}"
                return embed
            elif 'label' in action['data']:
                embed.description = f"📋 **Card:** {card_name}\n👤 **Updated By:** {member_name}"
                return embed
            return None
        elif action_type == 'commentCard':
            comment = action['data']['text']
            embed.description = f"📋 **Card:** {card_name}\n👤 **Comment By:** {member_name}"
            embed.add_field(name="💬 Comment", value=comment, inline=False)
            return embed
    
    embed.set_footer(text="Lexis Trello Updates")
    return None if action_type not in titles else embed

async def handle_card_move_to_resolved(action: dict):
    if 'listAfter' in action['data'] and action['data']['listAfter']['name'] == 'Resolved':
        card_id = action['data']['card']['id']
        list_before = action['data']['listBefore']['name']
        
        source_channel_id = None
        for config in CHANNEL_CONFIG.values():
            if 'list_name' in config and config['list_name'] == list_before:
                source_channel_id = config['channel_id']
                break
        
        if source_channel_id and source_channel_id in message_cache:
            channel = client.get_channel(source_channel_id)
            if channel and card_id in message_cache[source_channel_id]:
                try:
                    msg = await channel.fetch_message(message_cache[source_channel_id][card_id])
                    await msg.delete()
                    message_cache[source_channel_id].pop(card_id)
                except:
                    pass

@tasks.loop(seconds=30)
async def check_trello_updates():
    global last_action_id, is_first_run
    
    url = f'https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/actions'
    params = {'key': TRELLO_API_KEY, 'token': TRELLO_TOKEN, 'limit': 10}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        actions = response.json()
        
        if not actions or is_first_run:
            last_action_id = actions[0]['id'] if actions else None
            is_first_run = False
            return
        
        new_actions = []
        for action in actions:
            if action['id'] == last_action_id:
                break
            new_actions.append(action)
        
        if new_actions:
            last_action_id = new_actions[0]['id']
            updates_channel = client.get_channel(CHANNEL_CONFIG['trello-changes']['channel_id'])
            
            for action in reversed(new_actions):
                if updates_channel:
                    embed = format_trello_embed(action)
                    if embed is not None:
                        await updates_channel.send(embed=embed)
                if action['type'] == 'updateCard':
                    await handle_card_move_to_resolved(action)
            
            lists = await get_board_lists()
            for config in CHANNEL_CONFIG.values():
                if 'list_name' in config and config['list_name'] in lists:
                    channel = client.get_channel(config['channel_id'])
                    if channel:
                        await update_channel_cards(channel, config['list_name'], lists[config['list_name']])
                        
    except Exception as e:
        print(f"Error in check_trello_updates: {e}")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    
    channel = client.get_channel(CHANNEL_CONFIG['trello-changes']['channel_id'])
    if channel:
        embed = discord.Embed(
            title="🚀 Lexis Trello Bot Online",
            description="Tracking board updates across all channels!",
            color=0x2ECC71
        )
        embed.set_footer(text="Lexis Trello Updates")
        await channel.send(embed=embed)
    
    lists = await get_board_lists()
    for config in CHANNEL_CONFIG.values():
        if 'list_name' in config and config['list_name'] in lists:
            channel = client.get_channel(config['channel_id'])
            if channel:
                await update_channel_cards(channel, config['list_name'], lists[config['list_name']])
    
    await asyncio.sleep(5)
    check_trello_updates.start()

client.run(DISCORD_TOKEN)