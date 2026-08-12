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

# IDs de canales y roles
CANAL_IA_ID = 1536862569497624606
CANAL_SUGERENCIAS_ID = 1536466416851488828  # ID proporcionado
CANAL_LOGS_ID = 1536466416851488828  # Mismo ID para logs (puedes cambiarlo después)
CATEGORIA_TICKETS_ID = 1536466416851488828  # ID de la categoría de tickets

ROL_PERMITIDO_ID = 1519744694416965782
ROL_EXENTO_ID = 1519793995264294972
AUTO_ROLE_ID = 1508133051798917140
CANAL_PANEL_ID = 1519029606684823732
CANAL_BIENVENIDA = 1502668382640668853
CANAL_DESPEDIDA = 1502668463435419839

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
# FUNCIONES DE MANEJO DE DATOS
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
    warns = cargar_json(ARCHIVO_WARNS)
    user_id = str(member.id)
    warns[user_id] = warns.get(user_id, 0) + 1
    guardar_json(ARCHIVO_WARNS, warns)
    
    if canal:
        await canal.send(f"⚠️ {member.mention} ha recibido un warn por: {razon}. Total: {warns[user_id]}")
    
    if warns[user_id] >= 3:
        try:
            await member.ban(reason=f"3 warnings acumulados por {razon}")
            if canal:
                await canal.send(f"🚫 {member.mention} ha sido baneado por acumular 3 warnings.")
            del warns[user_id]
            guardar_json(ARCHIVO_WARNS, warns)
        except Exception as e:
            if canal:
                await canal.send(f"❌ Error al banear a {member.mention}: {e}")

def es_exento(member):
    roles_exentos = [ROL_PERMITIDO_ID, ROL_EXENTO_ID]
    for rol_id in roles_exentos:
        if discord.utils.get(member.roles, id=rol_id):
            return True
    return False

async def get_mute_role(guild):
    """Obtiene o crea el rol de mute"""
    mute_role = discord.utils.get(guild.roles, name="Muted")
    if not mute_role:
        mute_role = await guild.create_role(
            name="Muted", 
            permissions=discord.Permissions(0)
        )
        
        # Configurar permisos en todos los canales
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
    """Carga los mutes activos al iniciar el bot"""
    global mutes_activos
    mutes_data = cargar_json(ARCHIVO_MUTES)
    for guild_id, users in mutes_data.items():
        for user_id, end_time in users.items():
            mutes_activos[f"{guild_id}_{user_id}"] = end_time

async def guardar_mute(guild_id, user_id, end_time):
    """Guarda un mute en el archivo"""
    mutes = cargar_json(ARCHIVO_MUTES)
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)
    
    if guild_id_str not in mutes:
        mutes[guild_id_str] = {}
    mutes[guild_id_str][user_id_str] = end_time
    guardar_json(ARCHIVO_MUTES, mutes)

async def eliminar_mute(guild_id, user_id):
    """Elimina un mute del archivo"""
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
# FUNCIÓN PARA OBTENER CATEGORÍA DE TICKETS
# =============================================
async def obtener_categoria(guild):
    """Obtiene la categoría de tickets usando el ID proporcionado"""
    categoria = guild.get_channel(CATEGORIA_TICKETS_ID)
    if categoria:
        return categoria
    
    # Si no existe, crear una nueva
    categoria = discord.utils.get(guild.categories, name="TICKETS")
    if not categoria:
        categoria = await guild.create_category("TICKETS")
    return categoria

# =============================================
# MODAL PARA PREGUNTAR AL USUARIO (TICKETS)
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

            # Verificar si ya tiene ticket abierto
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

            # Log en el canal de logs
            canal_logs = bot.get_channel(CANAL_LOGS_ID)
            if canal_logs:
                log_embed = discord.Embed(
                    title="🎫 Nuevo Ticket",
                    description=f"**Usuario:** {usuario.mention}\n**Tipo:** {nombres.get(self.tipo_ticket, self.tipo_ticket)}\n**Canal:** {canal.mention}",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                await canal_logs.send(embed=log_embed)

            await interaction.followup.send(f"✅ Ticket creado: {canal.mention}", ephemeral=True)
            logger.info(f"Ticket creado por {usuario.name} en {canal.name}")

        except Exception as e:
            await interaction.followup.send(f"❌ Error al crear el ticket: {str(e)}", ephemeral=True)
            logger.error(f"Error al crear ticket: {e}")

# =============================================
# MODAL PARA NOTAS EN TICKETS
# =============================================
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
# SELECT DEL PANEL PRINCIPAL
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

# =============================================
# VISTA DEL PANEL
# =============================================
class PanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# =============================================
# BOTONES DE TICKET
# =============================================
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
                logger.info(f"Ticket {self.canal_id} cerrado por {interaction.user.name}")
            except Exception as e:
                await interaction.response.send_message(f"❌ Error al eliminar el canal: {e}", ephemeral=True)
                logger.error(f"Error al cerrar ticket: {e}")
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

# =============================================
# VISTA DESPUÉS DE CLAIM
# =============================================
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
    logger.info(f'✅ Bot conectado como {bot.user}')
    logger.info(f'📡 IA responderá en el canal: {CANAL_IA_ID}')
    logger.info(f'🎭 Auto-role asignará el rol ID: {AUTO_ROLE_ID}')
    logger.info(f'📊 Canal de sugerencias: {CANAL_SUGERENCIAS_ID}')
    logger.info(f'📝 Canal de logs: {CANAL_LOGS_ID}')
    logger.info(f'📁 Categoría de tickets: {CATEGORIA_TICKETS_ID}')
    logger.info(f'🔑 API Key de Groq: {"✅ Configurada" if GROQ_API_KEY else "❌ No configurada"}')
    
    # Cargar mutes activos
    await cargar_mutes()
    logger.info("✅ Mutes cargados correctamente")
    
    # Verificar canales
    canales_a_verificar = {
        'IA': CANAL_IA_ID,
        'Sugerencias': CANAL_SUGERENCIAS_ID,
        'Logs': CANAL_LOGS_ID,
        'Panel': CANAL_PANEL_ID,
        'Bienvenida': CANAL_BIENVENIDA,
        'Despedida': CANAL_DESPEDIDA
    }
    
    for nombre, id_canal in canales_a_verificar.items():
        canal = bot.get_channel(id_canal)
        if canal:
            logger.info(f'✅ Canal de {nombre} encontrado: {canal.name}')
        else:
            logger.warning(f'⚠️ Canal de {nombre} NO encontrado. ID: {id_canal}')
    
    # Enviar panel
    canal = bot.get_channel(CANAL_PANEL_ID)
    if canal:
        # Limpiar mensajes anteriores del panel
        try:
            async for msg in canal.history(limit=100):
                if msg.author == bot.user:
                    await msg.delete()
        except:
            pass
        
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
        logger.info(f"✅ Panel enviado a {canal.name}")
    else:
        logger.error("❌ Canal de panel no encontrado. Verifica el ID.")

# =============================================
# EVENTO DE BIENVENIDA + AUTO-ROLE + ANTI-RAID
# =============================================
@bot.event
async def on_member_join(member):
    # Detección de raid
    current_time = datetime.now().timestamp()
    raid_detection[member.guild.id].append(current_time)
    
    # Limpiar entradas viejas
    raid_detection[member.guild.id] = [
        t for t in raid_detection[member.guild.id] 
        if current_time - t < RAID_TIME_LIMIT
    ]
    
    if len(raid_detection[member.guild.id]) > RAID_JOIN_LIMIT:
        canal_logs = bot.get_channel(CANAL_LOGS_ID) if CANAL_LOGS_ID else None
        if canal_logs:
            embed = discord.Embed(
                title="🚨 POSIBLE RAID DETECTADO",
                description=f"**{len(raid_detection[member.guild.id])}** miembros se unieron en los últimos {RAID_TIME_LIMIT} segundos.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await canal_logs.send(embed=embed)
        logger.warning(f"🚨 Posible raid detectado en {member.guild.name}: {len(raid_detection[member.guild.id])} miembros")
    
    # Auto-role
    try:
        rol = member.guild.get_role(AUTO_ROLE_ID)
        if rol:
            await member.add_roles(rol)
            logger.info(f"✅ Rol asignado a {member.name} (ID: {member.id})")
        else:
            logger.error(f"❌ Rol con ID {AUTO_ROLE_ID} no encontrado")
    except discord.Forbidden:
        logger.error(f"❌ No tengo permisos para asignar roles en {member.guild.name}")
    except discord.HTTPException as e:
        logger.error(f"❌ Error al asignar rol: {e}")
    
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
            logger.info(f"🔇 Mute reactivado para {member.name}")

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
    
    # Log de salida
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if canal_logs:
        embed = discord.Embed(
            title="👋 Miembro Salido",
            description=f"**{member.name}** ha salido del servidor.",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Fecha de creación", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        await canal_logs.send(embed=embed)

# =============================================
# EVENTO ON_MESSAGE: MODERACIÓN + IA + COMANDOS
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
                logger.info(f"🚫 Mensaje eliminado de {message.author.name}: {razon}")
            except Exception as e:
                logger.error(f"❌ Error al aplicar moderación: {e}")

    # Comandos stick
    if message.content.lower().startswith('stick '):
        partes = message.content.split()
        if len(partes) >= 2:
            comando = partes[1].lower()
            
            if len(message.mentions) == 0:
                await message.channel.send("❌ Debes mencionar a un usuario: `stick warn/unwarn/ban/mute @usuario`")
                await bot.process_commands(message)
                return

            user = message.mentions[0]

            rol = discord.utils.get(message.author.roles, id=ROL_PERMITIDO_ID)
            if not rol:
                await message.channel.send("❌ No tienes el rol necesario para usar este comando.")
                await bot.process_commands(message)
                return

            if comando == 'warn':
                warns = cargar_json(ARCHIVO_WARNS)
                user_id = str(user.id)
                warns[user_id] = warns.get(user_id, 0) + 1
                guardar_json(ARCHIVO_WARNS, warns)

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
                        guardar_json(ARCHIVO_WARNS, warns)
                    except Exception as e:
                        await message.channel.send(f"❌ Error al banear: {e}")

            elif comando == 'unwarn':
                warns = cargar_json(ARCHIVO_WARNS)
                user_id = str(user.id)
                if user_id not in warns or warns[user_id] <= 0:
                    await message.channel.send(f"ℹ️ {user.mention} no tiene warnings para quitar.")
                    return

                warns[user_id] -= 1
                if warns[user_id] == 0:
                    del warns[user_id]
                guardar_json(ARCHIVO_WARNS, warns)

                await message.channel.send(f"✅ Se ha quitado un warn a {user.mention}. Ahora tiene {warns.get(user_id, 0)}.")

            elif comando == 'mute':
                if len(partes) < 4:
                    await message.channel.send("❌ Uso: `stick mute @usuario 5m razón`")
                    await bot.process_commands(message)
                    return
                
                tiempo = partes[2]
                razon = ' '.join(partes[3:]) if len(partes) > 3 else "Sin razón"
                
                # Parsear tiempo
                match = re.match(r'(\d+)([smhd])', tiempo.lower())
                if not match:
                    await message.channel.send("❌ Formato inválido. Usa: 5m, 1h, 1d")
                    await bot.process_commands(message)
                    return
                
                cantidad, unidad = match.groups()
                cantidad = int(cantidad)
                
                segundos = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}.get(unidad, 0)
                total_segundos = cantidad * segundos
                
                if total_segundos > 86400 * 7:  # Máximo 7 días
                    await message.channel.send("❌ No puedes mutear por más de 7 días.")
                    await bot.process_commands(message)
                    return
                
                mute_role = await get_mute_role(message.guild)
                await user.add_roles(mute_role)
                
                # Guardar mute
                end_time = datetime.now().timestamp() + total_segundos
                await guardar_mute(message.guild.id, user.id, end_time)
                mutes_activos[f"{message.guild.id}_{user.id}"] = end_time
                
                await message.channel.send(f"🔇 {user.mention} muteado por {cantidad}{unidad}. Razón: {razon}")
                logger.info(f"🔇 {user.name} muteado por {message.author.name} por {cantidad}{unidad}")
                
                # Desmutear automáticamente
                async def desmutear():
                    await asyncio.sleep(total_segundos)
                    try:
                        await user.remove_roles(mute_role)
                        await eliminar_mute(message.guild.id, user.id)
                        if f"{message.guild.id}_{user.id}" in mutes_activos:
                            del mutes_activos[f"{message.guild.id}_{user.id}"]
                        await message.channel.send(f"🔊 {user.mention} ha sido desmuteado automáticamente")
                        logger.info(f"🔊 {user.name} desmuteado automáticamente")
                    except Exception as e:
                        logger.error(f"Error al desmutear: {e}")
                
                bot.loop.create_task(desmutear())

            elif comando == 'unmute':
                mute_role = await get_mute_role(message.guild)
                if mute_role in user.roles:
                    await user.remove_roles(mute_role)
                    await eliminar_mute(message.guild.id, user.id)
                    if f"{message.guild.id}_{user.id}" in mutes_activos:
                        del mutes_activos[f"{message.guild.id}_{user.id}"]
                    await message.channel.send(f"🔊 {user.mention} ha sido desmuteado")
                    logger.info(f"🔊 {user.name} desmuteado por {message.author.name}")
                else:
                    await message.channel.send(f"ℹ️ {user.mention} no está muteado")

            elif comando == 'ban':
                bot_member = message.guild.me
                if not bot_member.guild_permissions.ban_members:
                    await message.channel.send("❌ El bot no tiene el permiso `Banear miembros`.")
                    return

                if user == message.author:
                    await message.channel.send("❌ No puedes banearte a ti mismo.")
                    return
                if user == bot.user:
                    await message.channel.send("❌ No puedes banear al bot.")
                    return
                if user == message.guild.owner:
                    await message.channel.send("❌ No puedo banear al propietario del servidor.")
                    return
                if bot_member.top_role <= user.top_role:
                    await message.channel.send(f"❌ Mi rol no es superior al de {user.mention}.")
                    return

                try:
                    await user.ban(reason=f"Baneado por {message.author} (comando stick ban)")
                    await message.channel.send(f"✅ {user.mention} ha sido baneado correctamente.")
                    logger.info(f"🔨 {user.name} baneado por {message.author.name}")
                except Exception as e:
                    await message.channel.send(f"❌ Error al banear: {e}")

    await bot.process_commands(message)

# =============================================
# COMANDO !panel
# =============================================
@bot.command(name='panel')
@commands.has_role(ROL_PERMITIDO_ID)
async def panel_cmd(ctx):
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
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()

# =============================================
# COMANDO suggest
# =============================================
@bot.command(name='suggest')
async def suggest(ctx, *, sugerencia):
    """!suggest Tu sugerencia aquí"""
    canal = bot.get_channel(CANAL_SUGERENCIAS_ID)
    if not canal:
        await ctx.send("❌ Canal de sugerencias no configurado.")
        return
    
    embed = discord.Embed(
        title="💡 Nueva Sugerencia",
        description=sugerencia,
        color=discord.Color.gold()
    )
    embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
    embed.set_footer(text=f"ID: {ctx.author.id} | {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    mensaje = await canal.send(embed=embed)
    await mensaje.add_reaction("✅")
    await mensaje.add_reaction("❌")
    await mensaje.add_reaction("🤷")
    
    await ctx.send("✅ Sugerencia enviada al canal de sugerencias.")
    logger.info(f"💡 Sugerencia de {ctx.author.name}: {sugerencia[:50]}...")

# =============================================
# COMANDOS DE ECONOMÍA
# =============================================
@bot.command(name='balance')
async def balance(ctx, miembro: discord.Member = None):
    """!balance @usuario - Ver monedas"""
    if miembro is None:
        miembro = ctx.author
    
    economia = cargar_json(ARCHIVO_ECONOMIA)
    user_id = str(miembro.id)
    monedas = economia.get(user_id, {}).get('monedas', 0)
    
    embed = discord.Embed(
        title="💰 Balance",
        description=f"{miembro.mention} tiene **{monedas}** monedas",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

@bot.command(name='give_coins')
@commands.has_permissions(administrator=True)
async def give_coins(ctx, miembro: discord.Member, cantidad: int):
    """!give_coins @usuario cantidad - Dar monedas (admin only)"""
    economia = cargar_json(ARCHIVO_ECONOMIA)
    user_id = str(miembro.id)
    
    if user_id not in economia:
        economia[user_id] = {'monedas': 0}
    
    economia[user_id]['monedas'] += cantidad
    guardar_json(ARCHIVO_ECONOMIA, economia)
    
    await ctx.send(f"✅ {cantidad} monedas agregadas a {miembro.mention}")
    logger.info(f"💰 {cantidad} monedas dadas a {miembro.name} por {ctx.author.name}")

# =============================================
# COMANDOS DE ESTADÍSTICAS
# =============================================
@bot.command(name='serverstats')
async def server_stats(ctx):
    """!serverstats - Estadísticas del servidor"""
    guild = ctx.guild
    
    total_members = guild.member_count
    humanos = sum(1 for m in guild.members if not m.bot)
    bots = total_members - humanos
    online = sum(1 for m in guild.members if m.status != discord.Status.offline)
    
    embed = discord.Embed(
        title=f"📊 Estadísticas de {guild.name}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="👥 Total", value=total_members, inline=True)
    embed.add_field(name="👤 Humanos", value=humanos, inline=True)
    embed.add_field(name="🤖 Bots", value=bots, inline=True)
    embed.add_field(name="🟢 Online", value=online, inline=True)
    embed.add_field(name="📅 Creado", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👑 Dueño", value=guild.owner.mention, inline=True)
    embed.add_field(name="📊 Canales", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='userinfo')
async def userinfo(ctx, miembro: discord.Member = None):
    """!userinfo @usuario - Información del usuario"""
    if miembro is None:
        miembro = ctx.author
    
    embed = discord.Embed(
        title=f"ℹ️ Información de {miembro.name}",
        color=miembro.color if miembro.color != discord.Color.default() else discord.Color.blue()
    )
    embed.set_thumbnail(url=miembro.display_avatar.url)
    embed.add_field(name="📛 Nombre", value=miembro.name, inline=True)
    embed.add_field(name="🔢 ID", value=miembro.id, inline=True)
    embed.add_field(name="📅 Creación", value=miembro.created_at.strftime("%d/%m/%Y %H:%M"), inline=True)
    embed.add_field(name="📥 Ingreso", value=miembro.joined_at.strftime("%d/%m/%Y %H:%M") if miembro.joined_at else "N/A", inline=True)
    embed.add_field(name="🎭 Roles", value=len(miembro.roles) - 1, inline=True)
    embed.add_field(name="🟢 Estado", value=miembro.status, inline=True)
    
    await ctx.send(embed=embed)

# =============================================
# COMANDOS DE BLACKLIST
# =============================================
@bot.command(name='blacklist')
@commands.has_permissions(administrator=True)
async def blacklist_cmd(ctx, accion: str, usuario: discord.Member = None):
    """!blacklist add/remove @usuario"""
    if usuario is None:
        await ctx.send("❌ Debes mencionar a un usuario.")
        return
    
    blacklist = cargar_json(ARCHIVO_BLACKLIST)
    user_id = str(usuario.id)
    
    if accion.lower() == 'add':
        if user_id not in blacklist.get('usuarios', []):
            if 'usuarios' not in blacklist:
                blacklist['usuarios'] = []
            blacklist['usuarios'].append(user_id)
            guardar_json(ARCHIVO_BLACKLIST, blacklist)
            await ctx.send(f"✅ {usuario.mention} agregado a la blacklist")
            logger.info(f"🚫 {usuario.name} agregado a la blacklist por {ctx.author.name}")
        else:
            await ctx.send(f"ℹ️ {usuario.mention} ya está en la blacklist")
    elif accion.lower() == 'remove':
        if user_id in blacklist.get('usuarios', []):
            blacklist['usuarios'].remove(user_id)
            guardar_json(ARCHIVO_BLACKLIST, blacklist)
            await ctx.send(f"✅ {usuario.mention} removido de la blacklist")
            logger.info(f"✅ {usuario.name} removido de la blacklist por {ctx.author.name}")
        else:
            await ctx.send(f"ℹ️ {usuario.mention} no está en la blacklist")
    else:
        await ctx.send("❌ Acción inválida. Usa `add` o `remove`")

# =============================================
# COMANDOS DE AUTO-ROLE
# =============================================
@bot.command(name='set_autorole')
@commands.has_permissions(administrator=True)
async def set_autorole(ctx, rol_id: int = None):
    """Cambia el rol que se asigna automáticamente (solo admins)"""
    global AUTO_ROLE_ID
    
    if rol_id is None:
        await ctx.send(f"🎭 Rol actual: <@&{AUTO_ROLE_ID}> (ID: {AUTO_ROLE_ID})")
        return
    
    rol = ctx.guild.get_role(rol_id)
    if rol is None:
        await ctx.send(f"❌ No se encontró el rol con ID {rol_id}")
        return
    
    AUTO_ROLE_ID = rol_id
    await ctx.send(f"✅ Rol auto-asignado actualizado a: {rol.mention}")

@bot.command(name='add_autorole')
@commands.has_permissions(administrator=True)
async def add_autorole(ctx, miembro: discord.Member = None):
    """Asigna manualmente el auto-role a un miembro (solo admins)"""
    if miembro is None:
        miembro = ctx.author
    
    rol = ctx.guild.get_role(AUTO_ROLE_ID)
    if rol is None:
        await ctx.send(f"❌ El rol con ID {AUTO_ROLE_ID} no existe")
        return
    
    if rol in miembro.roles:
        await ctx.send(f"ℹ️ {miembro.mention} ya tiene el rol {rol.mention}")
        return
    
    try:
        await miembro.add_roles(rol)
        await ctx.send(f"✅ Rol {rol.mention} asignado a {miembro.mention}")
    except Exception as e:
        await ctx.send(f"❌ Error al asignar el rol: {e}")

# =============================================
# COMANDOS DE IA
# =============================================
@bot.command(name='test_ia')
async def test_ia(ctx):
    if ctx.channel.id != CANAL_IA_ID:
        await ctx.send("❌ Este comando solo funciona en el canal de IA.")
        return
    
    await ctx.send("🤖 Bot de IA funcionando correctamente. Etiquétame con @bot y haz tu pregunta.")

@bot.command(name='set_ia_channel')
@commands.has_permissions(administrator=True)
async def set_ia_channel(ctx, canal_id: int = None):
    global CANAL_IA_ID
    
    if canal_id is None:
        await ctx.send(f"📡 Canal actual: <#{CANAL_IA_ID}>")
        return
    
    canal = bot.get_channel(canal_id)
    if canal is None:
        await ctx.send(f"❌ No se encontró el canal con ID {canal_id}")
        return
    
    CANAL_IA_ID = canal_id
    await ctx.send(f"✅ Canal de IA actualizado a: {canal.mention}")

@bot.command(name='test_apikey')
@commands.has_permissions(administrator=True)
async def test_apikey(ctx):
    """Prueba si la API key de Groq funciona"""
    await ctx.send("🔍 Probando API key de Groq...")
    
    resultado = await consultar_groq("Hola, ¿estás funcionando? Responde con un simple 'Sí'.")
    
    if "error" in resultado.lower() or "❌" in resultado:
        await ctx.send(f"❌ La API key NO funciona: {resultado}")
    else:
        await ctx.send(f"✅ La API key funciona correctamente!\n\nRespuesta de prueba: {resultado}")

# =============================================
# COMANDO clear_spam
# =============================================
@bot.command(name='clear_spam')
@commands.has_permissions(administrator=True)
async def clear_spam(ctx):
    global spam_counter
    spam_counter.clear()
    await ctx.send("✅ Contador de spam limpiado.")
    logger.info(f"🧹 Contador de spam limpiado por {ctx.author.name}")

# =============================================
# COMANDO DE ENCUESTA
# =============================================
@bot.command(name='poll')
async def poll(ctx, *, pregunta_y_opciones):
    """!poll "Pregunta" "Opción1" "Opción2" "Opción3" """
    # Extraer opciones entre comillas
    opciones = re.findall(r'"([^"]*)"', pregunta_y_opciones)
    
    if len(opciones) < 2:
        await ctx.send("❌ Necesitas al menos 2 opciones")
        return
    
    pregunta = opciones[0]
    opciones = opciones[1:]
    
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    embed = discord.Embed(
        title="📊 Encuesta",
        description=f"**{pregunta}**\n\n" + "\n".join([f"{emojis[i]} {opcion}" for i, opcion in enumerate(opciones[:10])]),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Encuesta creada por {ctx.author.name} | {datetime.now().strftime('%d/%m/%Y')}")
    
    mensaje = await ctx.send(embed=embed)
    
    for i in range(min(len(opciones), 10)):
        await mensaje.add_reaction(emojis[i])
    
    logger.info(f"📊 Encuesta creada por {ctx.author.name}: {pregunta}")

# =============================================
# COMANDO DE RECORDATORIO
# =============================================
@bot.command(name='remind')
async def remind(ctx, tiempo: str, *, recordatorio):
    """!remind 10s "Recordatorio" - 10s, 5m, 1h, 1d"""
    # Parsear tiempo
    match = re.match(r'(\d+)([smhd])', tiempo.lower())
    if not match:
        await ctx.send("❌ Formato inválido. Usa: 10s, 5m, 1h, 1d")
        return
    
    cantidad, unidad = match.groups()
    cantidad = int(cantidad)
    
    segundos = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }.get(unidad, 0)
    
    total_segundos = cantidad * segundos
    
    if total_segundos > 86400 * 7:  # Máximo 7 días
        await ctx.send("❌ No puedes programar recordatorios por más de 7 días.")
        return
    
    await ctx.send(f"✅ Recordatorio programado para {cantidad}{unidad}: {recordatorio}")
    
    await asyncio.sleep(total_segundos)
    await ctx.send(f"⏰ {ctx.author.mention}, recordatorio: **{recordatorio}**")
    logger.info(f"⏰ Recordatorio de {ctx.author.name}: {recordatorio}")

# =============================================
# INICIAR EL BOT
# =============================================
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"❌ Error al iniciar el bot: {e}")
