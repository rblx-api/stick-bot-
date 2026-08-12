import os
import json
import discord
from discord import ui
from discord.ext import commands
import re
from collections import defaultdict
import aiohttp
import logging
from datetime import datetime
import asyncio

# =============================================
# CONFIGURACIÓN DE LOGS
# =============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_logs.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================
# CONFIGURACIÓN
# =============================================
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise ValueError("❌ No se encontró el TOKEN. Configúralo en variables de entorno.")

GROQ_API_KEY = "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"
CANAL_IA_ID = 1536862569497624606

ROL_PERMITIDO_ID = 1519744694416965782
ROL_EXENTO_ID = 1519793995264294972
AUTO_ROLE_ID = 1508133051798917140
CANAL_PANEL_ID = 1519029606684823732
CANAL_BIENVENIDA = 1502668382640668853
CANAL_DESPEDIDA = 1502668463435419839
CATEGORIA_TICKETS_ID = 1536466416851488828
CANAL_SUGERENCIAS_ID = 1536466416851488828
CANAL_LOGS_ID = 1536466416851488828

# Archivos de datos
ARCHIVO_WARNS = 'warns.json'
ARCHIVO_BLACKLIST = 'blacklist.json'
ARCHIVO_ECONOMIA = 'economy.json'
ARCHIVO_MUTES = 'mutes.json'

# =============================================
# INTENTS Y BOT
# =============================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

tickets_activos = {}
spam_counter = defaultdict(list)
raid_detection = defaultdict(list)
mutes_activos = {}

SPAM_LIMIT = 5
SPAM_TIME = 10
RAID_JOIN_LIMIT = 5
RAID_TIME_LIMIT = 60

# =============================================
# FUNCIONES PARA MANEJO DE WARNS
# =============================================
def cargar_warns():
    if os.path.exists(ARCHIVO_WARNS):
        with open(ARCHIVO_WARNS, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def guardar_warns(warns):
    with open(ARCHIVO_WARNS, 'w', encoding='utf-8') as f:
        json.dump(warns, f, indent=4, ensure_ascii=False)

# =============================================
# FUNCIONES DE MANEJO DE ARCHIVOS JSON
# =============================================
def cargar_json(archivo, default=None):
    if default is None:
        default = {}
    if os.path.exists(archivo):
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default
    return default

def guardar_json(archivo, datos):
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

# =============================================
# FUNCIONES DE MODERACIÓN
# =============================================
def contiene_link(texto):
    patrones = [
        r'https?://[^\s]+',
        r'discord\.gg/[^\s]+',
        r'discord\.com/invite/[^\s]+',
        r'discordapp\.com/invite/[^\s]+',
        r'bit\.ly/[^\s]+',
        r'tinyurl\.com/[^\s]+',
        r'www\.[^\s]+\.[^\s]+'
    ]
    for patron in patrones:
        if re.search(patron, texto, re.IGNORECASE):
            return True
    return False

def contiene_nsfw(texto):
    palabras_nsfw = [
        'porno', 'xxx', 'nsfw', 'porn', 'chica', 'chicas',
        'mujer', 'mujeres', 'desnuda', 'desnudo', 'tetas',
        'culo', 'cojer', 'coger', 'sexo', 'sexual',
        'pornografía', 'pornografia', 'pene', 'vagina'
    ]
    texto_lower = texto.lower()
    for palabra in palabras_nsfw:
        if palabra in texto_lower:
            return True
    return False

def contiene_palabras_prohibidas(texto):
    palabras_prohibidas = [
        'check my bio', 'busco promotores', 'unanse a mi dc',
        'script gratis', 'loadstring', 'promotor', 'promotores',
        'bio', 'md', 'check mi bio', 'manden md', 'manda md',
        'pase script', 'paso script', 'promotor de script',
        'mi dc en bio', 'bio:', 'md:'
    ]
    texto_lower = texto.lower()
    for palabra in palabras_prohibidas:
        if palabra in texto_lower:
            return True
    return False

async def aplicar_warn(member, razon, canal=None):
    warns = cargar_warns()
    user_id = str(member.id)
    warns[user_id] = warns.get(user_id, 0) + 1
    guardar_warns(warns)
    
    if canal:
        await canal.send(f"⚠️ {member.mention} ha recibido un warn por: {razon}. Total: {warns[user_id]}")
    
    if warns[user_id] >= 3:
        try:
            await member.ban(reason=f"3 warnings acumulados por {razon}")
            if canal:
                await canal.send(f"🚫 {member.mention} ha sido baneado por acumular 3 warnings.")
            del warns[user_id]
            guardar_warns(warns)
        except Exception as e:
            if canal:
                await canal.send(f"❌ Error al banear a {member.mention}: {e}")

def es_exento(member):
    roles_exentos = [ROL_PERMITIDO_ID, ROL_EXENTO_ID]
    for rol_id in roles_exentos:
        if discord.utils.get(member.roles, id=rol_id):
            return True
    return False

# =============================================
# FUNCIONES PARA MUTES
# =============================================
async def get_mute_role(guild):
    mute_role = discord.utils.get(guild.roles, name="Muted")
    if not mute_role:
        mute_role = await guild.create_role(
            name="Muted", 
            permissions=discord.Permissions(0)
        )
        for channel in guild.channels:
            try:
                await channel.set_permissions(
                    mute_role, 
                    send_messages=False, 
                    add_reactions=False, 
                    speak=False,
                    connect=False
                )
            except:
                pass
    return mute_role

async def cargar_mutes():
    global mutes_activos
    mutes_data = cargar_json(ARCHIVO_MUTES)
    for guild_id, users in mutes_data.items():
        for user_id, end_time in users.items():
            mutes_activos[f"{guild_id}_{user_id}"] = end_time

async def guardar_mute(guild_id, user_id, end_time):
    mutes = cargar_json(ARCHIVO_MUTES)
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)
    
    if guild_id_str not in mutes:
        mutes[guild_id_str] = {}
    mutes[guild_id_str][user_id_str] = end_time
    guardar_json(ARCHIVO_MUTES, mutes)

async def eliminar_mute(guild_id, user_id):
    mutes = cargar_json(ARCHIVO_MUTES)
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)
    
    if guild_id_str in mutes and user_id_str in mutes[guild_id_str]:
        del mutes[guild_id_str][user_id_str]
        if not mutes[guild_id_str]:
            del mutes[guild_id_str]
        guardar_json(ARCHIVO_MUTES, mutes)

# =============================================
# FUNCIÓN DE IA PARA GROQ
# =============================================
async def consultar_groq(pregunta):
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "mixtral-8x7b-32768",
        "messages": [
            {"role": "system", "content": "Eres un asistente útil y amigable. Responde de manera clara y concisa en español."},
            {"role": "user", "content": pregunta}
        ],
        "temperature": 0.7,
        "max_tokens": 500,
        "top_p": 0.9
    }
    
    logger.info(f"🔍 Enviando pregunta a Groq: {pregunta[:100]}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as response:
                if response.status == 200:
                    resultado = await response.json()
                    respuesta = resultado['choices'][0]['message']['content']
                    logger.info(f"✅ Respuesta recibida de Groq: {respuesta[:100]}...")
                    return respuesta
                elif response.status == 401:
                    return "❌ La API key de Groq es inválida o ha expirado. Contacta al administrador."
                elif response.status == 429:
                    return "❌ Demasiadas peticiones a la IA. Espera un momento y vuelve a intentarlo."
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Error en la API de Groq: {response.status} - {error_text}")
                    return f"❌ Error {response.status}: La API de Groq no respondió correctamente."
    except aiohttp.ClientTimeout:
        return "❌ La IA tardó demasiado en responder. Intenta de nuevo con una pregunta más corta."
    except aiohttp.ClientError as e:
        logger.error(f"❌ Error de conexión con Groq: {e}")
        return "❌ Error de conexión con la API de Groq. Verifica tu conexión a internet."
    except Exception as e:
        logger.error(f"❌ Error al consultar la API de Groq: {e}")
        return f"❌ Error inesperado. Por favor, intenta de nuevo más tarde."

# =============================================
# FUNCIÓN PARA OBTENER/CREAR CATEGORÍA DE TICKETS
# =============================================
async def obtener_categoria(guild):
    if CATEGORIA_TICKETS_ID:
        categoria = guild.get_channel(CATEGORIA_TICKETS_ID)
        if categoria:
            return categoria
    categoria = discord.utils.get(guild.categories, name="TICKETS")
    if not categoria:
        categoria = await guild.create_category("TICKETS")
    return categoria

# =============================================
# MODALES PARA TICKETS
# =============================================
class PreguntaModal(ui.Modal, title="Responde la pregunta"):
    def __init__(self, tipo_ticket, usuario):
        super().__init__()
        self.tipo_ticket = tipo_ticket
        self.usuario = usuario
        if tipo_ticket in ["duels", "paid_sources"]:
            label = "💰 Monto a pagar"
            placeholder = "Describe el monto, método de pago, etc."
        elif tipo_ticket == "partner":
            label = "👥 Miembros"
            placeholder = "¿Cuántos miembros tiene tu servidor?"
        elif tipo_ticket == "report":
            label = "📢 Problema"
            placeholder = "Describe el problema que quieres reportar"
        else:
            label = "Consulta"
            placeholder = "Describe tu consulta"
        
        self.respuesta_input = ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            placeholder=placeholder,
            required=True,
            max_length=500
        )
        self.add_item(self.respuesta_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            respuesta = self.respuesta_input.value
            guild = interaction.guild
            usuario = self.usuario

            for channel_id, data in tickets_activos.items():
                if data['usuario_id'] == usuario.id and data['abierto']:
                    await interaction.followup.send("❌ Ya tienes un ticket abierto. Ciérralo antes de abrir otro.", ephemeral=True)
                    return

            categoria = await obtener_categoria(guild)
            nombre_canal = f"ticket-{usuario.name.lower().replace(' ', '-')}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                usuario: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            rol_autorizado = guild.get_role(ROL_PERMITIDO_ID)
            if rol_autorizado:
                overwrites[rol_autorizado] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            canal = await categoria.create_text_channel(nombre_canal, overwrites=overwrites)

            tickets_activos[canal.id] = {
                'usuario_id': usuario.id,
                'tipo': self.tipo_ticket,
                'abierto': True,
                'claimado_por': None,
                'canal': canal
            }

            nombres = {
                "duels": "Duelos ⚔️",
                "paid_sources": "Paid Sources 💰",
                "partner": "Partner / Alianzas 🤝",
                "report": "Reportar 📢"
            }

            embed = discord.Embed(
                title=f"Ticket de {usuario.name}",
                description=f"**Tipo:** {nombres.get(self.tipo_ticket, self.tipo_ticket)}\n\n**Respuesta:** {respuesta}\n\n*Un miembro del staff te atenderá.*",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"ID: {canal.id} | Abierto por {usuario.name}")

            view = TicketButtons(usuario.id, canal.id)
            await canal.send(
                f"{usuario.mention} {rol_autorizado.mention if rol_autorizado else ''}",
                embed=embed,
                view=view
            )

            await interaction.followup.send(f"✅ Ticket creado: {canal.mention}", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error al crear el ticket: {str(e)}", ephemeral=True)

class NotaModal(ui.Modal, title="Agregar Nota al Ticket"):
    nota = ui.TextInput(
        label="Nota",
        style=discord.TextStyle.paragraph,
        placeholder="Escribe la nota interna...",
        required=True,
        max_length=1000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        canal = interaction.channel
        await canal.send(f"📝 **Nota interna de {interaction.user.name}:**\n{self.nota.value}")
        await interaction.response.send_message("✅ Nota agregada", ephemeral=True)

# =============================================
# VISTAS DE TICKETS
# =============================================
class TicketSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Duelos", value="duels", description="Scripts y duelos", emoji="⚔️"),
            discord.SelectOption(label="Paid Sources", value="paid_sources", description="Fuentes pagadas", emoji="💰"),
            discord.SelectOption(label="Alianzas", value="partner", description="Alianzas y coordinación", emoji="🤝"),
            discord.SelectOption(label="Reportar", value="report", description="Reportar algo", emoji="📢"),
        ]
        super().__init__(placeholder="Elige una opción...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        valor = self.values[0]
        modal = PreguntaModal(valor, interaction.user)
        await interaction.response.send_modal(modal)

class PanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class TicketButtons(ui.View):
    def __init__(self, usuario_id, canal_id):
        super().__init__(timeout=None)
        self.usuario_id = usuario_id
        self.canal_id = canal_id

    @ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="cerrar_ticket")
    async def cerrar(self, interaction: discord.Interaction, button: ui.Button):
        rol = discord.utils.get(interaction.user.roles, id=ROL_PERMITIDO_ID)
        if not rol:
            await interaction.response.send_message("❌ No tienes permiso para cerrar tickets.", ephemeral=True)
            return

        if self.canal_id not in tickets_activos or not tickets_activos[self.canal_id]['abierto']:
            await interaction.response.send_message("❌ Este ticket ya está cerrado.", ephemeral=True)
            return

        tickets_activos[self.canal_id]['abierto'] = False
        canal = interaction.guild.get_channel(self.canal_id)
        if canal:
            try:
                await canal.delete()
                await interaction.response.send_message("✅ Ticket cerrado y canal eliminado.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error al eliminar el canal: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Canal no encontrado.", ephemeral=True)

    @ui.button(label="📌 Claim Ticket", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim(self, interaction: discord.Interaction, button: ui.Button):
        rol = discord.utils.get(interaction.user.roles, id=ROL_PERMITIDO_ID)
        if not rol:
            await interaction.response.send_message("❌ No tienes permiso para reclamar tickets.", ephemeral=True)
            return

        if self.canal_id not in tickets_activos or not tickets_activos[self.canal_id]['abierto']:
            await interaction.response.send_message("❌ Este ticket ya está cerrado.", ephemeral=True)
            return

        if tickets_activos[self.canal_id]['claimado_por'] is not None:
            await interaction.response.send_message("❌ Este ticket ya ha sido reclamado.", ephemeral=True)
            return

        tickets_activos[self.canal_id]['claimado_por'] = interaction.user.id
        
        usuario_id = tickets_activos[self.canal_id]['usuario_id']
        usuario = interaction.guild.get_member(usuario_id)

        nueva_vista = TicketButtonsAfterClaim(self.usuario_id, self.canal_id, interaction.user)
        await interaction.response.edit_message(view=nueva_vista)

        canal = interaction.guild.get_channel(self.canal_id)
        if canal:
            embed = discord.Embed(
                title="📌 Ticket reclamado",
                description=f"**{usuario.mention if usuario else 'Usuario'}, tu ticket ha sido reclamado por {interaction.user.mention}**\n\nEl staff se encargará de tu caso.",
                color=discord.Color.green()
            )
            await canal.send(embed=embed)

    @ui.button(label="📝 Agregar Nota", style=discord.ButtonStyle.secondary, custom_id="add_note")
    async def add_note(self, interaction: discord.Interaction, button: ui.Button):
        rol = discord.utils.get(interaction.user.roles, id=ROL_PERMITIDO_ID)
        if not rol:
            await interaction.response.send_message("❌ No tienes permiso para agregar notas.", ephemeral=True)
            return
        await interaction.response.send_modal(NotaModal())

class TicketButtonsAfterClaim(ui.View):
    def __init__(self, usuario_id, canal_id, quien_claimo):
        super().__init__(timeout=None)
        self.usuario_id = usuario_id
        self.canal_id = canal_id
        self.quien_claimo = quien_claimo

    @ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="cerrar_ticket_after")
    async def cerrar(self, interaction: discord.Interaction, button: ui.Button):
        rol = discord.utils.get(interaction.user.roles, id=ROL_PERMITIDO_ID)
        if not rol:
            await interaction.response.send_message("❌ No tienes permiso para cerrar tickets.", ephemeral=True)
            return

        if self.canal_id not in tickets_activos or not tickets_activos[self.canal_id]['abierto']:
            await interaction.response.send_message("❌ Este ticket ya está cerrado.", ephemeral=True)
            return

        tickets_activos[self.canal_id]['abierto'] = False
        canal = interaction.guild.get_channel(self.canal_id)
        if canal:
            try:
                await canal.delete()
                await interaction.response.send_message("✅ Ticket cerrado y canal eliminado.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error al eliminar el canal: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Canal no encontrado.", ephemeral=True)

    @ui.button(label="📝 Agregar Nota", style=discord.ButtonStyle.secondary, custom_id="add_note_after")
    async def add_note(self, interaction: discord.Interaction, button: ui.Button):
        rol = discord.utils.get(interaction.user.roles, id=ROL_PERMITIDO_ID)
        if not rol:
            await interaction.response.send_message("❌ No tienes permiso para agregar notas.", ephemeral=True)
            return
        await interaction.response.send_modal(NotaModal())

# =============================================
# EVENTO ON_READY
# =============================================
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'📡 IA responderá en el canal: {CANAL_IA_ID}')
    print(f'🎭 Auto-role asignará el rol ID: {AUTO_ROLE_ID}')
    print(f'🔑 API Key de Groq: {"✅ Configurada" if GROQ_API_KEY else "❌ No configurada"}')
    
    await cargar_mutes()
    print(f'✅ Mutes cargados correctamente')
    
    # Sincronizar slash commands
    try:
        synced = await bot.tree.sync()
        print(f'✅ Slash commands sincronizados: {len(synced)} comandos')
    except Exception as e:
        print(f'❌ Error al sincronizar slash commands: {e}')
    
    canal_ia = bot.get_channel(CANAL_IA_ID)
    if canal_ia:
        print(f'✅ Canal de IA encontrado: {canal_ia.name}')
    else:
        print(f'❌ Canal de IA NO encontrado. Verifica el ID: {CANAL_IA_ID}')
    
    canal = bot.get_channel(CANAL_PANEL_ID)
    if canal:
        embed = discord.Embed(
            title="═══════════════════════════════════════════════════════════",
            description=(
                "🔥🔥  𝐀𝐁𝐑𝐄 𝐓𝐈𝐂𝐊𝐄𝐓  𝐀𝐇𝐎𝐑𝐀  🔥🔥\n"
                "═══════════════════════════════════════════════════════════\n\n"
                "   ⚔️  Compra de Scripts de Duelos\n"
                "   💰  Paid Sources\n"
                "   🤝  Alianzas y Coordinación\n"
                "   📢  Reportar problemas\n\n"
                "   ✅ Atención 24/7\n"
                "   ✅ Soporte rápido y confiable\n"
                "   ✅ Trato directo sin rodeos\n\n"
                "   📩  ¡ABRE TU TICKET YA!\n"
                "   👉  No te quedes fuera\n\n"
                "═══════════════════════════════════════════════════════════\n"
                "   🔥🔥  𝐎𝐏𝐄𝐍  𝐀  𝐓𝐈𝐂𝐊𝐄𝐓  𝐍𝐎𝐖  🔥🔥\n"
                "═══════════════════════════════════════════════════════════\n\n"
                "   ⚔️  Duel Scripts Purchase\n"
                "   💰  Paid Sources\n"
                "   🤝  Alliances & Coordination\n"
                "   📢  Report issues\n\n"
                "   ✅ 24/7 Support\n"
                "   ✅ Fast and reliable service\n"
                "   ✅ Direct and clear deals\n\n"
                "   📩  OPEN YOUR TICKET NOW!\n"
                "   👉  Don't miss out\n\n"
                "═══════════════════════════════════════════════════════════"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Selecciona una opción en el menú desplegable para abrir tu ticket.")
        view = PanelView()
        await canal.send(embed=embed, view=view)
        print(f"✅ Panel enviado a {canal.name}")
    else:
        print("❌ Canal de panel no encontrado. Verifica el ID.")

# =============================================
# EVENTO DE BIENVENIDA + AUTO-ROLE + ANTI-RAID
# =============================================
@bot.event
async def on_member_join(member):
    # Detección de raid
    current_time = datetime.now().timestamp()
    raid_detection[member.guild.id].append(current_time)
    
    raid_detection[member.guild.id] = [
        t for t in raid_detection[member.guild.id] 
        if current_time - t < RAID_TIME_LIMIT
    ]
    
    if len(raid_detection[member.guild.id]) > RAID_JOIN_LIMIT:
        canal_logs = bot.get_channel(CANAL_LOGS_ID)
        if canal_logs:
            embed = discord.Embed(
                title="🚨 POSIBLE RAID DETECTADO",
                description=f"**{len(raid_detection[member.guild.id])}** miembros se unieron en los últimos {RAID_TIME_LIMIT} segundos.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await canal_logs.send(embed=embed)
        print(f"🚨 Posible raid detectado en {member.guild.name}: {len(raid_detection[member.guild.id])} miembros")
    
    # Auto-role
    try:
        rol = member.guild.get_role(AUTO_ROLE_ID)
        if rol:
            await member.add_roles(rol)
            print(f"✅ Rol asignado a {member.name} (ID: {member.id})")
        else:
            print(f"❌ Rol con ID {AUTO_ROLE_ID} no encontrado")
    except discord.Forbidden:
        print(f"❌ No tengo permisos para asignar roles en {member.guild.name}")
    except discord.HTTPException as e:
        print(f"❌ Error al asignar rol: {e}")
    
    # Mensaje de bienvenida
    canal = bot.get_channel(CANAL_BIENVENIDA)
    if canal:
        embed = discord.Embed(
            title="¡Bienvenido a Stick Hub!",
            description=f"{member.mention} espero disfrutes del servidor 🎉",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Miembro #{member.guild.member_count}")
        await canal.send(embed=embed)
    
    # Verificar mutes activos
    key = f"{member.guild.id}_{member.id}"
    if key in mutes_activos:
        end_time = mutes_activos[key]
        if datetime.now().timestamp() < end_time:
            mute_role = await get_mute_role(member.guild)
            await member.add_roles(mute_role)
            print(f"🔇 Mute reactivado para {member.name}")

# =============================================
# EVENTO DE DESPEDIDA
# =============================================
@bot.event
async def on_member_remove(member):
    canal = bot.get_channel(CANAL_DESPEDIDA)
    if canal:
        embed = discord.Embed(
            description=f"{member.mention} gracias por haber sido parte de Stick Hub, espero volverte a ver 👋",
            color=discord.Color.red()
        )
        embed.set_image(url=member.display_avatar.url)
        await canal.send(embed=embed)

# =============================================
# EVENTO ON_MESSAGE: MODERACIÓN + IA + COMANDOS STICK
# =============================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Verificar blacklist
    blacklist = cargar_json(ARCHIVO_BLACKLIST)
    if str(message.author.id) in blacklist.get('usuarios', []):
        try:
            await message.delete()
            await message.author.send("❌ Estás en la blacklist del servidor.")
        except:
            pass
        return

    # Sistema de IA
    if message.channel.id == CANAL_IA_ID:
        if bot.user.mentioned_in(message):
            contenido = message.content
            for mention in message.mentions:
                if mention.id == bot.user.id:
                    contenido = contenido.replace(f'<@{mention.id}>', '').replace(f'<@!{mention.id}>', '').strip()
            
            if not contenido:
                await message.reply("❓ ¿Qué necesitas saber? Hazme una pregunta.")
                return
            
            thinking_message = await message.reply("🤔 Pensando...")
            respuesta = await consultar_groq(contenido)
            
            if len(respuesta) > 1900:
                respuesta = respuesta[:1900] + "..."
            
            try:
                await thinking_message.edit(content=respuesta)
            except Exception as e:
                await thinking_message.edit(content=f"❌ Error al mostrar la respuesta: {e}")
        
        await bot.process_commands(message)
        return

    # Sistema de moderación automática
    if not es_exento(message.author):
        mensaje_borrado = False
        razon = None
        contenido = message.content

        if contiene_link(contenido):
            razon = "No se permiten enlaces"
            mensaje_borrado = True
        elif contiene_nsfw(contenido):
            razon = "Contenido inapropiado (NSFW)"
            mensaje_borrado = True
        elif contiene_palabras_prohibidas(contenido):
            razon = "Palabras prohibidas (promoción no autorizada)"
            mensaje_borrado = True
        else:
            user_id = message.author.id
            current_time = message.created_at.timestamp()
            spam_counter[user_id] = [t for t in spam_counter[user_id] if current_time - t < SPAM_TIME]
            spam_counter[user_id].append(current_time)
            
            if len(spam_counter[user_id]) > SPAM_LIMIT:
                razon = "Spam (más de 5 mensajes en 10 segundos)"
                mensaje_borrado = True

        if mensaje_borrado:
            try:
                await message.delete()
                await aplicar_warn(message.author, razon, message.channel)
                
                embed = discord.Embed(
                    title="⚠️ Moderación Automática",
                    description=f"**{message.author.mention}** tu mensaje ha sido eliminado por: **{razon}**",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed, delete_after=10)
            except Exception as e:
                print(f"❌ Error al aplicar moderación: {e}")

    # Comandos stick (mantenemos los comandos con prefijo para compatibilidad)
    if message.content.lower().startswith('stick '):
        partes = message.content.split()
        if len(partes) >= 2:
            comando = partes[1].lower()
            
            if len(message.mentions) == 0:
                await message.channel.send("❌ Debes mencionar a un usuario: `stick warn/unwarn/ban/mute/unmute @usuario`")
                await bot.process_commands(message)
                return

            user = message.mentions[0]

            rol = discord.utils.get(message.author.roles, id=ROL_PERMITIDO_ID)
            if not rol:
                await message.channel.send("❌ No tienes el rol necesario para usar este comando.")
                await bot.process_commands(message)
                return

            if comando == 'warn':
                warns = cargar_warns()
                user_id = str(user.id)
                warns[user_id] = warns.get(user_id, 0) + 1
                guardar_warns(warns)

                await message.channel.send(f"⚠️ {user.mention} ha recibido un warn. Total: {warns[user_id]}")

                if warns[user_id] >= 3:
                    if not message.guild.me.guild_permissions.ban_members:
                        await message.channel.send("❌ El bot no tiene permisos para banear.")
                        return

                    if user == message.guild.owner:
                        await message.channel.send("❌ No puedo banear al propietario del servidor.")
                        return

                    if message.guild.me.top_role <= user.top_role:
                        await message.channel.send(f"❌ Mi rol no es superior al de {user.mention}.")
                        return

                    try:
                        await user.ban(reason="3 warnings acumulados (ban automático)")
                        await message.channel.send(f"🚫 {user.mention} ha sido baneado por acumular 3 warnings.")
                        del warns[user_id]
                        guardar_warns(warns)
                    except Exception as e:
                        await message.channel.send(f"❌ Error al banear: {e}")

            elif comando == 'unwarn':
                warns = cargar_warns()
                user_id = str(user.id)
                if user_id not in warns or warns[user_id] <= 0:
                    await message.channel.send(f"ℹ️ {user.mention} no tiene warnings para quitar.")
                    return

                warns[user_id] -= 1
                if warns[user_id] == 0:
                    del warns[user_id]
                guardar_warns(warns)

                await message.channel.send(f"✅ Se ha quitado un warn a {user.mention}. Ahora tiene {warns.get(user_id, 0)}.")

            elif comando == 'mute':
                if len(partes) < 4:
                    await message.channel.send("❌ Uso: `stick mute @usuario 5m razón`")
                    await bot.process_commands(message)
                    return
                
                tiempo = partes[2]
                raz
