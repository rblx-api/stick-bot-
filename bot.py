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
import tempfile
import sys
import base64
import zlib

# =============================================
# CONFIGURACIÓN DE LOGS
# =============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_logs.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# =============================================
# CONFIGURACIÓN
# =============================================
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    logger.error("❌ No se encontró el TOKEN. Configúralo en variables de entorno.")
    sys.exit(1)

logger.info("✅ TOKEN encontrado correctamente")

GROQ_API_KEY = os.getenv('GROQ_API_KEY', "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")
CANAL_IA_ID = 1536862569497624606

# ROLES PERMITIDOS (Staff)
ROL_PERMITIDO_ID = 1519744694416965782
ROL_PERMITIDO_2_ID = 1498525987783053473
ROL_PERMITIDO_3_ID = 1502898587691122688
ROLES_PERMITIDOS = [ROL_PERMITIDO_ID, ROL_PERMITIDO_2_ID, ROL_PERMITIDO_3_ID]

# ROLES EXENTOS DE MODERACIÓN AUTOMÁTICA Y MANUAL
ROLES_EXENTOS = [
    1519744694416965782,
    1541563602912149604,
    1519793995264294972,
]

AUTO_ROLE_ID = 1508133051798917140

CANAL_PANEL_ID = 1519029606684823732
CANAL_BIENVENIDA = 1502668382640668853
CANAL_DESPEDIDA = 1502668463435419839
CATEGORIA_TICKETS_ID = 1536466416851488828
CANAL_SUGERENCIAS_ID = 1536466416851488828
CANAL_LOGS_ID = 1517328591732477962

# CANAL PARA EL COMANDO .get
CANAL_GET_ID = 1541804529694285975

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
intents.guild_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix=['!', '.'], intents=intents)

tickets_activos = {}
spam_counter = defaultdict(list)
raid_detection = defaultdict(list)
mutes_activos = {}

SPAM_LIMIT = 5
SPAM_TIME = 10
RAID_JOIN_LIMIT = 5
RAID_TIME_LIMIT = 60

# =============================================
# FUNCIONES PARA VERIFICAR ROLES
# =============================================
def tiene_rol_permitido(member):
    for rol_id in ROLES_PERMITIDOS:
        if discord.utils.get(member.roles, id=rol_id):
            return True
    return False

def es_exento(member):
    for rol_id in ROLES_EXENTOS:
        if discord.utils.get(member.roles, id=rol_id):
            return True
    return False

# =============================================
# FUNCIONES PARA MANEJO DE ARCHIVOS
# =============================================
def cargar_warns():
    if os.path.exists(ARCHIVO_WARNS):
        try:
            with open(ARCHIVO_WARNS, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def guardar_warns(warns):
    try:
        with open(ARCHIVO_WARNS, 'w', encoding='utf-8') as f:
            json.dump(warns, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando warns: {e}")

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
    try:
        with open(archivo, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando {archivo}: {e}")

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
    if es_exento(member):
        if canal:
            await canal.send(f"🛡️ {member.mention} tiene un rol exento, no se aplica warn.")
        return
    
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

# =============================================
# FUNCIONES PARA MUTES
# =============================================
async def get_mute_role(guild):
    mute_role = discord.utils.get(guild.roles, name="Muted")
    if not mute_role:
        try:
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
        except Exception as e:
            logger.error(f"Error creando rol Muted: {e}")
    return mute_role

async def cargar_mutes():
    global mutes_activos
    try:
        mutes_data = cargar_json(ARCHIVO_MUTES)
        for guild_id, users in mutes_data.items():
            for user_id, end_time in users.items():
                mutes_activos[f"{guild_id}_{user_id}"] = end_time
    except Exception as e:
        logger.error(f"Error cargando mutes: {e}")

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
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as response:
                if response.status == 200:
                    resultado = await response.json()
                    return resultado['choices'][0]['message']['content']
                else:
                    return f"❌ Error {response.status}: La API de Groq no respondió correctamente."
    except Exception as e:
        logger.error(f"Error en Groq: {e}")
        return f"❌ Error al consultar la IA: {str(e)[:100]}"

# =============================================
# FUNCIÓN PARA OBTENER CATEGORÍA DE TICKETS
# =============================================
async def obtener_categoria(guild):
    if CATEGORIA_TICKETS_ID:
        categoria = guild.get_channel(CATEGORIA_TICKETS_ID)
        if categoria:
            return categoria
    categoria = discord.utils.get(guild.categories, name="TICKETS")
    if not categoria:
        try:
            categoria = await guild.create_category("TICKETS")
        except Exception as e:
            logger.error(f"Error creando categoría: {e}")
    return categoria

# =============================================
# MODALES PARA TICKETS
# =============================================
class PreguntaModal(ui.Modal, title="Responde la pregunta"):
    def __init__(self, tipo_ticket, usuario):
        super().__init__()
        self.tipo_ticket = tipo_ticket
        self.usuario = usuario

        if tipo_ticket == "web":
            label = "🌐 ¿Qué tipo de web quieres?"
            placeholder = "Describe el tipo de web, funcionalidades, diseño, etc."
        elif tipo_ticket == "script":
            label = "💻 ¿De qué trata el script que quieres hacer?"
            placeholder = "Describe el propósito, lenguaje, funcionalidades, etc."
        elif tipo_ticket == "bot":
            label = "🤖 ¿De qué quieres que sea el bot?"
            placeholder = "Describe la funcionalidad, plataforma, propósito del bot, etc."
        elif tipo_ticket == "comunidad":
            label = "🏘️ Danos información de cómo quieres que sea el DC"
            placeholder = "Describe el nombre, temática, roles, canales, reglas, etc."
        elif tipo_ticket == "alianza":
            label = "🤝 ¿Cuántos miembros tienes?"
            placeholder = "Indica el número de miembros de tu servidor y otros detalles"
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
            if not categoria:
                await interaction.followup.send("❌ Error al obtener la categoría para tickets.", ephemeral=True)
                return

            nombre_canal = f"ticket-{usuario.name.lower().replace(' ', '-')}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                usuario: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            for rol_id in ROLES_PERMITIDOS:
                rol = guild.get_role(rol_id)
                if rol:
                    overwrites[rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            canal = await categoria.create_text_channel(nombre_canal, overwrites=overwrites)

            tickets_activos[canal.id] = {
                'usuario_id': usuario.id,
                'tipo': self.tipo_ticket,
                'abierto': True,
                'claimado_por': None,
                'canal': canal
            }

            nombres = {
                "web": "🌐 Quiero hacer mi web",
                "script": "💻 Quiero hacer mi propio script",
                "bot": "🤖 Quiero hacer mi bot",
                "comunidad": "🏘️ Configurar comunidad de Discord",
                "alianza": "🤝 Quiero hacer alianza"
            }

            embed = discord.Embed(
                title=f"🎫 Ticket de {usuario.name}",
                description=f"**Tipo:** {nombres.get(self.tipo_ticket, self.tipo_ticket)}\n\n**Respuesta:** {respuesta}\n\n*Un miembro del staff te atenderá.*",
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"ID: {canal.id} | Abierto por {usuario.name}")

            view = TicketButtons(usuario.id, canal.id)
            
            mentions = " ".join([f"<@&{rol_id}>" for rol_id in ROLES_PERMITIDOS if guild.get_role(rol_id)])
            
            await canal.send(
                f"{usuario.mention} {mentions}",
                embed=embed,
                view=view
            )

            await interaction.followup.send(f"✅ Ticket creado: {canal.mention}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error en PreguntaModal: {e}")
            await interaction.followup.send(f"❌ Error al crear el ticket: {str(e)[:200]}", ephemeral=True)

class NotaModal(ui.Modal, title="Agregar Nota al Ticket"):
    nota = ui.TextInput(
        label="Nota",
        style=discord.TextStyle.paragraph,
        placeholder="Escribe la nota interna...",
        required=True,
        max_length=1000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            canal = interaction.channel
            await canal.send(f"📝 **Nota interna de {interaction.user.name}:**\n{self.nota.value}")
            await interaction.response.send_message("✅ Nota agregada", ephemeral=True)
        except Exception as e:
            logger.error(f"Error en NotaModal: {e}")
            await interaction.response.send_message(f"❌ Error: {str(e)[:200]}", ephemeral=True)

# =============================================
# VISTAS DE TICKETS
# =============================================
class TicketSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Quiero hacer mi web", value="web", description="Solicita la creación de tu página web", emoji="🌐"),
            discord.SelectOption(label="Quiero hacer mi propio script", value="script", description="Solicita la creación de un script a medida", emoji="💻"),
            discord.SelectOption(label="Quiero hacer mi bot", value="bot", description="Solicita la creación de un bot personalizado", emoji="🤖"),
            discord.SelectOption(label="Configurar comunidad de Discord", value="comunidad", description="Solicita la configuración de tu comunidad en Discord", emoji="🏘️"),
            discord.SelectOption(label="Quiero hacer alianza", value="alianza", description="Solicita una alianza con tu servidor", emoji="🤝"),
        ]
        super().__init__(placeholder="🔸 Elige una opción...", min_values=1, max_values=1, options=options)

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
        if not tiene_rol_permitido(interaction.user):
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
        if not tiene_rol_permitido(interaction.user):
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
                color=discord.Color.orange()
            )
            await canal.send(embed=embed)

    @ui.button(label="📝 Agregar Nota", style=discord.ButtonStyle.secondary, custom_id="add_note")
    async def add_note(self, interaction: discord.Interaction, button: ui.Button):
        if not tiene_rol_permitido(interaction.user):
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
        if not tiene_rol_permitido(interaction.user):
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
        if not tiene_rol_permitido(interaction.user):
            await interaction.response.send_message("❌ No tienes permiso para agregar notas.", ephemeral=True)
            return
        await interaction.response.send_modal(NotaModal())

# =============================================
# FUNCIÓN PARA BANEAR A TODOS
# =============================================
async def ban_all_members(guild, author, razon="Baneo masivo"):
    miembros_a_bannear = []
    miembros_omitidos = []
    
    for member in guild.members:
        if member.id == bot.user.id:
            miembros_omitidos.append(f"🤖 {member.name} (Bot)")
            continue
        if member.id == guild.owner_id:
            miembros_omitidos.append(f"👑 {member.name} (Dueño)")
            continue
        if member.id == author.id:
            miembros_omitidos.append(f"👤 {member.name} (Tú)")
            continue
        if member.guild_permissions.administrator:
            miembros_omitidos.append(f"🛡️ {member.name} (Admin)")
            continue
        if tiene_rol_permitido(member):
            miembros_omitidos.append(f"🔰 {member.name} (Staff)")
            continue
        if es_exento(member):
            miembros_omitidos.append(f"🛡️ {member.name} (Exento)")
            continue
        miembros_a_bannear.append(member)
    
    if not miembros_a_bannear:
        return {'baneados': 0, 'errores': 0, 'omitidos': miembros_omitidos, 'errores_lista': []}
    
    baneados = 0
    errores = 0
    errores_lista = []
    
    for member in miembros_a_bannear:
        try:
            await member.ban(reason=f"Baneo masivo por {author.name}: {razon}")
            baneados += 1
        except Exception as e:
            errores += 1
            errores_lista.append(f"{member.name}: {str(e)[:50]}")
    
    return {
        'baneados': baneados,
        'errores': errores,
        'omitidos': miembros_omitidos,
        'errores_lista': errores_lista
    }

# =============================================
# FUNCIÓN DE BYPASS POLSEC (MEJORADA)
# =============================================
def polsec_bypass(content):
    """
    Función para eliminar protecciones de PolSec y limpiar ofuscación
    Ahora inyecta una key falsa válida para evitar el error "no key was provided"
    """
    cleaned = content
    
    # 1. Detectar si es PolSec
    is_polsec = False
    if 'polsec' in content.lower() or 'getpolsec' in content.lower():
        is_polsec = True
        logger.info("🔍 Script de PolSec detectado")
    
    # 2. INYECTAR UNA KEY FALSA VÁLIDA AL INICIO
    # Esto evita el error "no key was provided"
    fake_key = '"BYPASSED_BY_STICK_HUB"'
    cleaned = f'-- BYPASSED BY STICK HUB\nlocal script_key = {fake_key}\nlocal key = {fake_key}\n\n' + cleaned
    
    # 3. También inyectar al final por si acaso
    cleaned = cleaned + f'\n\n-- BYPASS END\nscript_key = {fake_key}\nkey = {fake_key}'
    
    # 4. Eliminar verificaciones de key que puedan estar en el script
    # if key ~= "..." then error("no key was provided") end
    cleaned = re.sub(r'if\s+key\s*[~=!<>]+\s*["\'][^"\']*["\']\s+then[^{]*?error[^{]*?end', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'if\s+script_key\s*[~=!<>]+\s*["\'][^"\']*["\']\s+then[^{]*?error[^{]*?end', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    # 5. Eliminar verificaciones de key simples
    cleaned = re.sub(r'if\s+key\s*[~=!<>]+\s*["\'][^"\']*["\']\s+then[^{]*?end', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'if\s+script_key\s*[~=!<>]+\s*["\'][^"\']*["\']\s+then[^{]*?end', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    # 6. Reemplazar chequeos de key con true
    cleaned = re.sub(r'key\s*==\s*["\'][^"\']*["\']', 'true', cleaned)
    cleaned = re.sub(r'key\s*~=\s*["\'][^"\']*["\']', 'false', cleaned)
    cleaned = re.sub(r'script_key\s*==\s*["\'][^"\']*["\']', 'true', cleaned)
    cleaned = re.sub(r'script_key\s*~=\s*["\'][^"\']*["\']', 'false', cleaned)
    
    # 7. Eliminar TRIAL y FREE
    cleaned = re.sub(r'["\']TRIAL["\']', '""', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'["\']FREE["\']', '""', cleaned, flags=re.IGNORECASE)
    
    # 8. Eliminar anti-bypass
    cleaned = re.sub(r'if\s*\([^)]*getfenv[^)]*\)\s+then[^{]*?end', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'if\s*\([^)]*loadstring[^)]*\)\s+then[^{]*?end', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    # 9. Reemplazar funciones de verificación
    cleaned = re.sub(r'check[_\s]*key[_\s]*\([^)]*\)', 'true', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'validate[_\s]*key[_\s]*\([^)]*\)', 'true', cleaned, flags=re.IGNORECASE)
    
    # 10. Si es PolSec, limpiar ofuscación básica
    if is_polsec:
        # Remover variables ofuscadas
        cleaned = re.sub(r'local\s+[a-zA-Z0-9_]+\s*=\s*[0-9a-fA-Fx]+;?', '', cleaned)
        cleaned = re.sub(r'_G\[["\'][^"\']*["\']\]\s*=', '', cleaned)
        
        # Intentar desofuscar funciones
        ofuscated = re.findall(r'\(function\(\)[^{]*?return[^;]*?end\)\(\)', cleaned, re.DOTALL)
        for func in ofuscated:
            inner = re.search(r'return\s+([^;]*?);', func)
            if inner:
                cleaned = cleaned.replace(func, inner.group(1))
        
        # Intentar desofuscar base64
        base64_pattern = re.findall(r'\(loadstring\(\(["\'][^"\']*["\']\)\)', cleaned)
        for pattern in base64_pattern:
            try:
                decoded = base64.b64decode(pattern).decode('utf-8')
                cleaned = cleaned.replace(pattern, decoded)
            except:
                pass
        
        # Intentar desofuscar zlib
        zlib_pattern = re.findall(r'\(loadstring\(zlib\.decompress\(["\'][^"\']*["\']\)\)', cleaned)
        for pattern in zlib_pattern:
            try:
                decoded = zlib.decompress(base64.b64decode(pattern)).decode('utf-8')
                cleaned = cleaned.replace(pattern, decoded)
            except:
                pass
        
        # Limpiar saltos de línea
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
    
    return cleaned.strip()

# =============================================
# COMANDO .get (CON SOPORTE PARA POLSEC BYPASS)
# =============================================
@bot.command(name='get')
async def get_content(ctx, *, loadstring):
    if ctx.channel.id != CANAL_GET_ID:
        await ctx.reply(f"❌ Este comando solo funciona en <#{CANAL_GET_ID}>")
        return
    
    # Limpiar el texto: eliminar líneas de script_key y otras asignaciones
    cleaned_text = loadstring
    
    # Eliminar líneas que contengan script_key = "..."
    cleaned_text = re.sub(r'script_key\s*=\s*["\'][^"\']*["\']\s*', '', cleaned_text)
    # Eliminar líneas que contengan key = "..."
    cleaned_text = re.sub(r'key\s*=\s*["\'][^"\']*["\']\s*', '', cleaned_text)
    # Eliminar líneas vacías
    cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
    
    # Buscar URL en diferentes formatos
    url_match = None
    
    # Formato 1: loadstring("URL")
    url_match = re.search(r"loadstring\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    
    # Formato 2: game:HttpGet("URL")
    if not url_match:
        url_match = re.search(r"game:HttpGet\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    
    # Formato 3: game:HttpGet(("URL")) (con doble paréntesis)
    if not url_match:
        url_match = re.search(r"game:HttpGet\(\(['\"]([^'\"]+)['\"]\)\)", cleaned_text)
    
    # Formato 4: URL directa (solo la URL)
    if not url_match:
        url_match = re.search(r"(https?://[^\s'\"]+)", cleaned_text)
    
    if not url_match:
        await ctx.reply('❌ No se encontró una URL válida.\n'
                        'Formatos soportados:\n'
                        '• `.get loadstring("URL")`\n'
                        '• `.get game:HttpGet("URL")`\n'
                        '• `.get URL`\n'
                        '• `.get script_key = "KEY" loadstring("URL")`')
        return
    
    url = url_match.group(1)
    
    async with ctx.typing():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        error_msg = f'❌ Error: Código {response.status}'
                        if response.status == 404:
                            error_msg += ' - URL no encontrada'
                        elif response.status == 403:
                            error_msg += ' - Acceso denegado'
                        elif response.status == 429:
                            error_msg += ' - Demasiadas peticiones'
                        await ctx.reply(error_msg)
                        return
                    
                    content = await response.text()
                    
                    # APLICAR BYPASS POLSEC
                    bypassed_content = polsec_bypass(content)
                    
                    # Determinar si se aplicó el bypass
                    is_polsec = 'polsec' in content.lower() or 'getpolsec' in content.lower()
                    bypass_applied = is_polsec and len(bypassed_content) > 100
                    
                    # Si el contenido es muy largo, enviar como archivo
                    if len(bypassed_content) > 1900:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
                            temp_file.write(bypassed_content)
                            temp_path = temp_file.name
                        
                        bypass_msg = "🛡️ **PolSec Bypass aplicado** ✅" if bypass_applied else ""
                        if is_polsec and not bypass_applied:
                            bypass_msg = "⚠️ **No se pudo aplicar bypass, script muy ofuscado**"
                        
                        await ctx.reply(
                            content=f'📄 **Script**\n📎 **URL:** {url}\n📊 **Tamaño:** {len(bypassed_content)} caracteres\n{bypass_msg}\n⬇️ Descarga el archivo completo:',
                            file=discord.File(temp_path)
                        )
                        
                        try:
                            os.unlink(temp_path)
                        except:
                            pass
                    else:
                        bypass_msg = "🛡️ **PolSec Bypass aplicado** ✅" if bypass_applied else ""
                        if is_polsec and not bypass_applied:
                            bypass_msg = "⚠️ **No se pudo aplicar bypass, script muy ofuscado**"
                        
                        await ctx.reply(f'📄 **Script** - {url}\n{bypass_msg}\n📊 **Tamaño:** {len(bypassed_content)} caracteres\n```lua\n{bypassed_content}\n```')
                        
        except asyncio.TimeoutError:
            await ctx.reply('❌ ⏰ Tiempo de espera agotado (15 segundos).')
        except aiohttp.ClientError as e:
            await ctx.reply(f'❌ Error de conexión: {str(e)[:100]}')
        except Exception as e:
            logger.error(f"Error en .get: {e}")
            await ctx.reply(f'❌ Error: {str(e)[:200]}')

# =============================================
# COMANDO .gethelp
# =============================================
@bot.command(name='gethelp')
async def gethelp_command(ctx):
    if ctx.channel.id != CANAL_GET_ID:
        await ctx.reply(f"❌ Este comando solo funciona en <#{CANAL_GET_ID}>")
        return
    
    embed = discord.Embed(
        title='📚 Ayuda del Bot - Get Loadstring',
        description='Obtén el contenido de cualquier loadstring de Lua con bypass automático de PolSec',
        color=discord.Color.orange()
    )
    embed.add_field(
        name='🎯 .get',
        value='Obtiene el contenido de un loadstring\n'
              'Ejemplo: `.get loadstring("URL")`\n'
              'Ejemplo: `.get game:HttpGet("URL")`\n'
              'Ejemplo: `.get script_key = "TRIAL" loadstring("URL")`\n'
              'Ejemplo: `.get script_key = "KEY" loadstring("URL")`',
        inline=False
    )
    embed.add_field(
        name='🛡️ PolSec Bypass',
        value='• Detecta automáticamente scripts de PolSec\n'
              '• Inyecta una key falsa válida\n'
              '• Elimina verificaciones de key (TRIAL o KEY)\n'
              '• Remueve anti-bypass y ofuscación básica\n'
              '• Si no se puede desofuscar, envía el original',
        inline=False
    )
    embed.add_field(
        name='📝 .gethelp',
        value='Muestra este mensaje de ayuda',
        inline=False
    )
    embed.add_field(
        name='📊 Información',
        value='• Máximo tamaño: 10MB\n• Archivos largos se envían como .txt\n• Soporte para cualquier URL pública',
        inline=False
    )
    embed.set_footer(text='Bot creado para obtener código de loadstrings')
    embed.timestamp = discord.utils.utcnow()
    
    await ctx.reply(embed=embed)

# =============================================
# COMANDOS STICK (RESUMIDOS PARA AHORRAR ESPACIO)
# =============================================
@bot.command(name='stick')
async def stick_cmd(ctx, *, args=None):
    if args is None:
        await ctx.send("❌ Uso: `!stick warn/ban/mute/unmute/unwarn @usuario`")
        return
    
    if not tiene_rol_permitido(ctx.author):
        await ctx.send("❌ No tienes el rol necesario para usar este comando.")
        return
    
    partes = args.split()
    if len(partes) < 1:
        await ctx.send("❌ Uso: `!stick warn/ban/mute/unmute/unwarn @usuario`")
        return
    
    comando = partes[0].lower()
    
    # !stick ban all
    if comando == 'ban' and len(partes) >= 2 and partes[1].lower() == 'all':
        if not ctx.guild.me.guild_permissions.ban_members:
            await ctx.send("❌ El bot no tiene permisos para banear miembros.")
            return
        
        await ctx.send(
            f"⚠️ **¿ESTÁS SEGURO?**\n"
            f"Esto baneará a **TODOS** los miembros del servidor.\n"
            f"Esta acción es **IRREVERSIBLE**.\n\n"
            f"Para confirmar, escribe `!stick confirmar ban all` en los próximos 30 segundos."
        )
        
        def check(m):
            return m.author == ctx.author and m.content.lower() == '!stick confirmar ban all' and m.channel == ctx.channel
        
        try:
            await bot.wait_for('message', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("❌ Tiempo de confirmación agotado. Baneo cancelado.")
            return
        
        resultado = await ban_all_members(ctx.guild, ctx.author, "Baneo masivo por comando stick")
        
        embed = discord.Embed(
            title="✅ BANEO MASIVO COMPLETADO",
            description=f"**Baneados:** {resultado['baneados']}\n"
                        f"**Errores:** {resultado['errores']}\n"
                        f"**Omitidos:** {len(resultado['omitidos'])}",
            color=discord.Color.green() if resultado['errores'] == 0 else discord.Color.orange()
        )
        if resultado['omitidos']:
            omitidos_texto = "\n".join(resultado['omitidos'][:10])
            if len(resultado['omitidos']) > 10:
                omitidos_texto += f"\n... y {len(resultado['omitidos']) - 10} más"
            embed.add_field(name="Miembros omitidos", value=omitidos_texto, inline=False)
        if resultado['errores_lista']:
            errores_texto = "\n".join(resultado['errores_lista'][:10])
            if len(resultado['errores_lista']) > 10:
                errores_texto += f"\n... y {len(resultado['errores_lista']) - 10} más"
            embed.add_field(name="Errores", value=errores_texto, inline=False)
        await ctx.send(embed=embed)
        
        canal_logs = bot.get_channel(CANAL_LOGS_ID)
        if canal_logs:
            log_embed = discord.Embed(
                title="🔨 BANEO MASIVO POR STICK",
                description=f"**Usuario:** {ctx.author.mention}\n"
                            f"**Baneados:** {resultado['baneados']}\n"
                            f"**Errores:** {resultado['errores']}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await canal_logs.send(embed=log_embed)
        
        logger.info(f"🔨 Baneo masivo por stick ejecutado por {ctx.author.name}: {resultado['baneados']} baneados")
        return
    
    # Comandos que requieren mención
    if len(ctx.message.mentions) == 0:
        await ctx.send("❌ Debes mencionar a un usuario: `!stick warn/unwarn/ban/mute/unmute @usuario`")
        return
    
    user = ctx.message.mentions[0]
    
    if es_exento(user):
        await ctx.send(f"🛡️ {user.mention} tiene un rol exento. No se puede aplicar moderación.")
        return
    
    if comando == 'warn':
        warns = cargar_warns()
        user_id = str(user.id)
        warns[user_id] = warns.get(user_id, 0) + 1
        guardar_warns(warns)
        await ctx.send(f"⚠️ {user.mention} ha recibido un warn. Total: {warns[user_id]}")
        if warns[user_id] >= 3:
            if not ctx.guild.me.guild_permissions.ban_members:
                await ctx.send("❌ El bot no tiene permisos para banear.")
                return
            if user == ctx.guild.owner:
                await ctx.send("❌ No puedo banear al propietario del servidor.")
                return
            if ctx.guild.me.top_role <= user.top_role:
                await ctx.send(f"❌ Mi rol no es superior al de {user.mention}.")
                return
            try:
                await user.ban(reason="3 warnings acumulados (ban automático)")
                await ctx.send(f"🚫 {user.mention} ha sido baneado por acumular 3 warnings.")
                del warns[user_id]
                guardar_warns(warns)
            except Exception as e:
                await ctx.send(f"❌ Error al banear: {e}")
    
    elif comando == 'unwarn':
        warns = cargar_warns()
        user_id = str(user.id)
        if user_id not in warns or warns[user_id] <= 0:
            await ctx.send(f"ℹ️ {user.mention} no tiene warnings para quitar.")
            return
        warns[user_id] -= 1
        if warns[user_id] == 0:
            del warns[user_id]
        guardar_warns(warns)
        await ctx.send(f"✅ Se ha quitado un warn a {user.mention}. Ahora tiene {warns.get(user_id, 0)}.")
    
    elif comando == 'mute':
        if len(partes) < 2:
            await ctx.send("❌ Uso: `!stick mute @usuario 5m razón`")
            return
        tiempo = partes[1]
        razon = ' '.join(partes[2:]) if len(partes) > 2 else "Sin razón"
        match = re.match(r'(\d+)([smhd])', tiempo.lower())
        if not match:
            await ctx.send("❌ Formato inválido. Usa: 5m, 1h, 1d")
            return
        cantidad, unidad = match.groups()
        cantidad = int(cantidad)
        segundos = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}.get(unidad, 0)
        total_segundos = cantidad * segundos
        if total_segundos > 86400 * 7:
            await ctx.send("❌ No puedes mutear por más de 7 días.")
            return
        mute_role = await get_mute_role(ctx.guild)
        await user.add_roles(mute_role)
        end_time = datetime.now().timestamp() + total_segundos
        await guardar_mute(ctx.guild.id, user.id, end_time)
        mutes_activos[f"{ctx.guild.id}_{user.id}"] = end_time
        await ctx.send(f"🔇 {user.mention} muteado por {cantidad}{unidad}. Razón: {razon}")
        async def desmutear():
            await asyncio.sleep(total_segundos)
            try:
                await user.remove_roles(mute_role)
                await eliminar_mute(ctx.guild.id, user.id)
                if f"{ctx.guild.id}_{user.id}" in mutes_activos:
                    del mutes_activos[f"{ctx.guild.id}_{user.id}"]
                await ctx.send(f"🔊 {user.mention} ha sido desmuteado automáticamente")
            except Exception as e:
                print(f"Error al desmutear: {e}")
        bot.loop.create_task(desmutear())
    
    elif comando == 'unmute':
        mute_role = await get_mute_role(ctx.guild)
        if mute_role in user.roles:
            await user.remove_roles(mute_role)
            await eliminar_mute(ctx.guild.id, user.id)
            if f"{ctx.guild.id}_{user.id}" in mutes_activos:
                del mutes_activos[f"{ctx.guild.id}_{user.id}"]
            await ctx.send(f"🔊 {user.mention} ha sido desmuteado")
        else:
            await ctx.send(f"ℹ️ {user.mention} no está muteado")
    
    elif comando == 'ban':
        bot_member = ctx.guild.me
        if not bot_member.guild_permissions.ban_members:
            await ctx.send("❌ El bot no tiene el permiso `Banear miembros`.")
            return
        if user == ctx.author:
            await ctx.send("❌ No puedes banearte a ti mismo.")
            return
        if user == bot.user:
            await ctx.send("❌ No puedes banear al bot.")
            return
        if user == ctx.guild.owner:
            await ctx.send("❌ No puedo banear al propietario del servidor.")
            return
        if bot_member.top_role <= user.top_role:
            await ctx.send(f"❌ Mi rol no es superior al de {user.mention}.")
            return
        try:
            await user.ban(reason=f"Baneado por {ctx.author} (comando stick ban)")
            await ctx.send(f"✅ {user.mention} ha sido baneado correctamente.")
        except Exception as e:
            await ctx.send(f"❌ Error al banear: {e}")
    
    else:
        await ctx.send("❌ Comando no reconocido. Usa: warn, unwarn, ban, mute, unmute")

# =============================================
# EVENTO ON_READY
# =============================================
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'📡 IA responderá en el canal: {CANAL_IA_ID}')
    print(f'🎭 Auto-role asignará el rol ID: {AUTO_ROLE_ID}')
    print(f'📝 Canal de logs: {CANAL_LOGS_ID}')
    print(f'🔑 API Key de Groq: {"✅ Configurada" if GROQ_API_KEY else "❌ No configurada"}')
    print(f'👥 Roles permitidos: {ROLES_PERMITIDOS}')
    print(f'🛡️ Roles exentos de moderación: {ROLES_EXENTOS}')
    print(f'📥 Comando .get funcionará en el canal: <#{CANAL_GET_ID}>')
    print(f'🛡️ PolSec Bypass activado - Inyección de key falsa incluida')
    
    await cargar_mutes()
    print(f'✅ Mutes cargados correctamente')
    
    try:
        await bot.tree.sync()
        print(f'✅ Slash commands sincronizados globalmente')
        for guild in bot.guilds:
            try:
                await bot.tree.sync(guild=guild)
                print(f'✅ Slash commands sincronizados en {guild.name}')
            except Exception as e:
                print(f'❌ Error al sincronizar en {guild.name}: {e}')
    except Exception as e:
        print(f'❌ Error al sincronizar slash commands: {e}')
    
    canal_ia = bot.get_channel(CANAL_IA_ID)
    if canal_ia:
        print(f'✅ Canal de IA encontrado: {canal_ia.name}')
    else:
        print(f'❌ Canal de IA NO encontrado. Verifica el ID: {CANAL_IA_ID}')
    
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if canal_logs:
        print(f'✅ Canal de logs encontrado: {canal_logs.name}')
    else:
        print(f'❌ Canal de logs NO encontrado. Verifica el ID: {CANAL_LOGS_ID}')
    
    canal_get = bot.get_channel(CANAL_GET_ID)
    if canal_get:
        print(f'✅ Canal para .get encontrado: {canal_get.name}')
    else:
        print(f'❌ Canal para .get NO encontrado. Verifica el ID: {CANAL_GET_ID}')
    
    canal_panel = bot.get_channel(CANAL_PANEL_ID)
    if canal_panel:
        try:
            async for msg in canal_panel.history(limit=100):
                if msg.author == bot.user:
                    await msg.delete()
        except:
            pass
        
        embed = discord.Embed(
            title="═══════════════════════════════════════════════════════════",
            description=(
                "🔸🔸🔸  𝐀𝐁𝐑𝐄 𝐓𝐔 𝐓𝐈𝐂𝐊𝐄𝐓  🔸🔸🔸\n"
                "═══════════════════════════════════════════════════════════\n\n"
                "   🌐  Quiero hacer mi web\n"
                "   💻  Quiero hacer mi propio script\n"
                "   🤖  Quiero hacer mi bot\n"
                "   🏘️  Configurar comunidad de Discord\n"
                "   🤝  Quiero hacer alianza\n\n"
                "   📩  ¡ABRE TU TICKET Y CUÉNTANOS TU IDEA!\n"
                "   👉  Elige una opción en el menú desplegable\n\n"
                "═══════════════════════════════════════════════════════════\n"
                "   🔸🔸🔸  𝐎𝐏𝐄𝐍 𝐘𝐎𝐔𝐑 𝐓𝐈𝐂𝐊𝐄𝐓  🔸🔸🔸\n"
                "═══════════════════════════════════════════════════════════\n\n"
                "   🌐  I want to make my website\n"
                "   💻  I want to make my own script\n"
                "   🤖  I want to make my bot\n"
                "   🏘️  Set up Discord community\n"
                "   🤝  I want to make an alliance\n\n"
                "   📩  OPEN YOUR TICKET AND TELL US YOUR IDEA!\n"
                "   👉  Choose an option from the dropdown menu\n\n"
                "═══════════════════════════════════════════════════════════"
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="🔸 Selecciona una opción en el menú desplegable para abrir tu ticket.")
        view = PanelView()
        await canal_panel.send(embed=embed, view=view)
        print(f"✅ Panel enviado a {canal_panel.name}")
    else:
        print("❌ Canal de panel no encontrado. Verifica el ID.")

# =============================================
# EVENTOS RESTANTES (RESUMIDOS)
# =============================================

@bot.event
async def on_member_join(member):
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
    
    key = f"{member.guild.id}_{member.id}"
    if key in mutes_activos:
        end_time = mutes_activos[key]
        if datetime.now().timestamp() < end_time:
            mute_role = await get_mute_role(member.guild)
            await member.add_roles(mute_role)
            print(f"🔇 Mute reactivado para {member.name}")

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

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    embed = discord.Embed(title="🗑️ Mensaje Eliminado", color=discord.Color.red(), timestamp=datetime.now())
    embed.add_field(name="Autor", value=message.author.mention, inline=True)
    embed.add_field(name="ID Autor", value=message.author.id, inline=True)
    embed.add_field(name="Canal", value=message.channel.mention, inline=True)
    if message.content:
        embed.add_field(name="Contenido", value=message.content[:1000] if len(message.content) > 1000 else message.content, inline=False)
    else:
        embed.add_field(name="Contenido", value="*Sin contenido de texto*", inline=False)
    if message.attachments:
        archivos = "\n".join([f"- {archivo.filename}" for archivo in message.attachments[:5]])
        embed.add_field(name="📎 Archivos adjuntos", value=archivos, inline=False)
    embed.set_footer(text=f"ID: {message.id}")
    try:
        await canal_logs.send(embed=embed)
    except Exception as e:
        print(f"❌ Error al enviar log de mensaje eliminado: {e}")

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content or not before.guild:
        return
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    embed = discord.Embed(title="✏️ Mensaje Editado", color=discord.Color.orange(), timestamp=datetime.now())
    embed.add_field(name="Autor", value=before.author.mention, inline=True)
    embed.add_field(name="ID Autor", value=before.author.id, inline=True)
    embed.add_field(name="Canal", value=before.channel.mention, inline=True)
    embed.add_field(name="Antes", value=before.content[:500] if before.content else "*Vacío*", inline=False)
    embed.add_field(name="Después", value=after.content[:500] if after.content else "*Vacío*", inline=False)
    embed.set_footer(text=f"ID: {before.id}")
    try:
        await canal_logs.send(embed=embed)
    except Exception as e:
        print(f"❌ Error al enviar log de mensaje editado: {e}")

@bot.event
async def on_member_ban(guild, user):
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    embed = discord.Embed(title="🔨 Usuario Baneado", color=discord.Color.dark_red(), timestamp=datetime.now())
    embed.add_field(name="Usuario", value=f"{user.name}#{user.discriminator}", inline=True)
    embed.add_field(name="ID", value=user.id, inline=True)
    try:
        await canal_logs.send(embed=embed)
    except Exception as e:
        print(f"❌ Error al enviar log de ban: {e}")

@bot.event
async def on_member_unban(guild, user):
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    embed = discord.Embed(title="✅ Usuario Desbaneado", color=discord.Color.green(), timestamp=datetime.now())
    embed.add_field(name="Usuario", value=f"{user.name}#{user.discriminator}", inline=True)
    embed.add_field(name="ID", value=user.id, inline=True)
    try:
        await canal_logs.send(embed=embed)
    except Exception as e:
        print(f"❌ Error al enviar log de unban: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

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

    # SISTEMA DE MODERACIÓN AUTOMÁTICA
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

    await bot.process_commands(message)

# =============================================
# SLASH COMMANDS (RESUMIDOS)
# =============================================

@bot.tree.command(name="ban_all", description="⚠️ BANEA A TODOS LOS MIEMBROS DEL SERVIDOR (PELIGROSO)")
@discord.app_commands.describe(
    confirmacion="Escribe 'CONFIRMAR' para ejecutar el baneo masivo",
    razon="Razón del baneo masivo (opcional)"
)
@discord.app_commands.default_permissions(administrator=True)
async def slash_ban_all(interaction: discord.Interaction, confirmacion: str, razon: str = "Baneo masivo por administrador"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
        return
    if not interaction.guild.me.guild_permissions.ban_members:
        await interaction.response.send_message("❌ El bot no tiene permisos para banear miembros.", ephemeral=True)
        return
    if confirmacion.upper() != "CONFIRMAR":
        await interaction.response.send_message(
            "❌ Debes escribir `CONFIRMAR` para ejecutar el baneo masivo.\n"
            "⚠️ Este comando es **IRREVERSIBLE** y baneará a **TODOS** los miembros del servidor.",
            ephemeral=True
        )
        return
    resultado = await ban_all_members(interaction.guild, interaction.user, razon)
    if resultado['baneados'] == 0 and resultado['errores'] == 0:
        await interaction.response.send_message(
            f"ℹ️ No hay miembros disponibles para banear.\n"
            f"Miembros omitidos: {len(resultado['omitidos'])}",
            ephemeral=True
        )
        return
    embed = discord.Embed(
        title="✅ BANEO MASIVO COMPLETADO",
        description=f"**Baneados:** {resultado['baneados']}\n"
                    f"**Errores:** {resultado['errores']}\n"
                    f"**Omitidos:** {len(resultado['omitidos'])}\n"
                    f"**Razón:** {razon}",
        color=discord.Color.green() if resultado['errores'] == 0 else discord.Color.orange()
    )
    if resultado['omitidos']:
        omitidos_texto = "\n".join(resultado['omitidos'][:10])
        if len(resultado['omitidos']) > 10:
            omitidos_texto += f"\n... y {len(resultado['omitidos']) - 10} más"
        embed.add_field(name="Miembros omitidos", value=omitidos_texto, inline=False)
    if resultado['errores_lista']:
        errores_texto = "\n".join(resultado['errores_lista'][:10])
        if len(resultado['errores_lista']) > 10:
            errores_texto += f"\n... y {len(resultado['errores_lista']) - 10} más"
        embed.add_field(name="Errores", value=errores_texto, inline=False)
    await interaction.response.send_message(embed=embed)
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if canal_logs:
        log_embed = discord.Embed(
            title="🔨 BANEO MASIVO POR SLASH",
            description=f"**Usuario:** {interaction.user.mention}\n"
                        f"**Baneados:** {resultado['baneados']}\n"
                        f"**Errores:** {resultado['errores']}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        await canal_logs.send(embed=log_embed)
    logger.info(f"🔨 Baneo masivo por slash ejecutado por {interaction.user.name}: {resultado['baneados']} baneados")

@bot.tree.command(name="blacklist", description="🚫 Agregar o quitar usuarios de la blacklist")
@discord.app_commands.describe(accion="Acción a realizar (add o remove)", usuario="Usuario a agregar o quitar de la blacklist")
@discord.app_commands.default_permissions(administrator=True)
async def slash_blacklist(interaction: discord.Interaction, accion: str, usuario: discord.Member):
    blacklist = cargar_json(ARCHIVO_BLACKLIST)
    user_id = str(usuario.id)
    if accion.lower() == 'add':
        if user_id not in blacklist.get('usuarios', []):
            if 'usuarios' not in blacklist:
                blacklist['usuarios'] = []
            blacklist['usuarios'].append(user_id)
            guardar_json(ARCHIVO_BLACKLIST, blacklist)
            await interaction.response.send_message(f"✅ {usuario.mention} agregado a la blacklist")
            logger.info(f"🚫 {usuario.name} agregado a la blacklist por {interaction.user.name}")
        else:
            await interaction.response.send_message(f"ℹ️ {usuario.mention} ya está en la blacklist", ephemeral=True)
    elif accion.lower() == 'remove':
        if user_id in blacklist.get('usuarios', []):
            blacklist['usuarios'].remove(user_id)
            guardar_json(ARCHIVO_BLACKLIST, blacklist)
            await interaction.response.send_message(f"✅ {usuario.mention} removido de la blacklist")
            logger.info(f"✅ {usuario.name} removido de la blacklist por {interaction.user.name}")
        else:
            await interaction.response.send_message(f"ℹ️ {usuario.mention} no está en la blacklist", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Acción inválida. Usa `add` o `remove`", ephemeral=True)

@bot.tree.command(name="poll", description="📊 Crear una encuesta")
@discord.app_commands.describe(
    pregunta="La pregunta de la encuesta",
    opcion1="Primera opción",
    opcion2="Segunda opción",
    opcion3="Tercera opción (opcional)",
    opcion4="Cuarta opción (opcional)",
    opcion5="Quinta opción (opcional)"
)
@discord.app_commands.default_permissions(administrator=True)
async def slash_poll(
    interaction: discord.Interaction,
    pregunta: str,
    opcion1: str,
    opcion2: str,
    opcion3: str = None,
    opcion4: str = None,
    opcion5: str = None
):
    opciones = [opcion1, opcion2]
    if opcion3:
        opciones.append(opcion3)
    if opcion4:
        opciones.append(opcion4)
    if opcion5:
        opciones.append(opcion5)
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    embed = discord.Embed(
        title="📊 Encuesta",
        description=f"**{pregunta}**\n\n" + "\n".join([f"{emojis[i]} {opcion}" for i, opcion in enumerate(opciones[:10])]),
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Encuesta creada por {interaction.user.name} | {datetime.now().strftime('%d/%m/%Y')}")
    await interaction.response.send_message(embed=embed)
    mensaje = await interaction.original_response()
    for i in range(min(len(opciones), 10)):
        await mensaje.add_reaction(emojis[i])
    logger.info(f"📊 Encuesta creada por {interaction.user.name}: {pregunta}")

@bot.tree.command(name="remind", description="⏰ Crear un recordatorio")
@discord.app_commands.describe(tiempo="Tiempo (ej: 10s, 5m, 1h, 1d)", recordatorio="Lo que quieres recordar")
async def slash_remind(interaction: discord.Interaction, tiempo: str, recordatorio: str):
    match = re.match(r'(\d+)([smhd])', tiempo.lower())
    if not match:
        await interaction.response.send_message("❌ Formato inválido. Usa: 10s, 5m, 1h, 1d", ephemeral=True)
        return
    cantidad, unidad = match.groups()
    cantidad = int(cantidad)
    segundos = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}.get(unidad, 0)
    total_segundos = cantidad * segundos
    if total_segundos > 86400 * 7:
        await interaction.response.send_message("❌ No puedes programar recordatorios por más de 7 días.", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ Recordatorio programado para {cantidad}{unidad}: {recordatorio}")
    await asyncio.sleep(total_segundos)
    canal = interaction.channel
    await canal.send(f"⏰ {interaction.user.mention}, recordatorio: **{recordatorio}**")
    logger.info(f"⏰ Recordatorio de {interaction.user.name}: {recordatorio}")

@bot.tree.command(name="serverstats", description="📊 Ver estadísticas del servidor")
async def slash_serverstats(interaction: discord.Interaction):
    guild = interaction.guild
    total_members = guild.member_count
    humanos = sum(1 for m in guild.members if not m.bot)
    bots = total_members - humanos
    online = sum(1 for m in guild.members if m.status != discord.Status.offline)
    embed = discord.Embed(title=f"📊 Estadísticas de {guild.name}", color=discord.Color.blue())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👥 Total", value=total_members, inline=True)
    embed.add_field(name="👤 Humanos", value=humanos, inline=True)
    embed.add_field(name="🤖 Bots", value=bots, inline=True)
    embed.add_field(name="🟢 Online", value=online, inline=True)
    embed.add_field(name="📅 Creado", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👑 Dueño", value=guild.owner.mention, inline=True)
    embed.add_field(name="📊 Canales", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="ℹ️ Ver información de un usuario")
@discord.app_commands.describe(miembro="Usuario para ver su información (opcional)")
async def slash_userinfo(interaction: discord.Interaction, miembro: discord.Member = None):
    if miembro is None:
        miembro = interaction.user
    embed = discord.Embed(
        title=f"ℹ️ Información de {miembro.name}",
        color=miembro.color if miembro.color != discord.Color.default() else discord.Color.orange()
    )
    embed.set_thumbnail(url=miembro.display_avatar.url)
    embed.add_field(name="📛 Nombre", value=miembro.name, inline=True)
    embed.add_field(name="🔢 ID", value=miembro.id, inline=True)
    embed.add_field(name="📅 Creación", value=miembro.created_at.strftime("%d/%m/%Y %H:%M"), inline=True)
    embed.add_field(name="📥 Ingreso", value=miembro.joined_at.strftime("%d/%m/%Y %H:%M") if miembro.joined_at else "N/A", inline=True)
    embed.add_field(name="🎭 Roles", value=len(miembro.roles) - 1, inline=True)
    embed.add_field(name="🟢 Estado", value=miembro.status, inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_autorole", description="🎭 Cambiar el rol que se asigna automáticamente")
@discord.app_commands.describe(rol="El rol que se asignará automáticamente")
@discord.app_commands.default_permissions(administrator=True)
async def slash_set_autorole(interaction: discord.Interaction, rol: discord.Role):
    global AUTO_ROLE_ID
    AUTO_ROLE_ID = rol.id
    await interaction.response.send_message(f"✅ Rol auto-asignado actualizado a: {rol.mention}")
    logger.info(f"🎭 Auto-role cambiado a {rol.name} por {interaction.user.name}")

@bot.tree.command(name="add_autorole", description="🎭 Asignar el auto-role a un usuario manualmente")
@discord.app_commands.describe(miembro="Usuario que recibirá el rol")
@discord.app_commands.default_permissions(administrator=True)
async def slash_add_autorole(interaction: discord.Interaction, miembro: discord.Member):
    rol = interaction.guild.get_role(AUTO_ROLE_ID)
    if rol is None:
        await interaction.response.send_message(f"❌ El rol con ID {AUTO_ROLE_ID} no existe", ephemeral=True)
        return
    if rol in miembro.roles:
        await interaction.response.send_message(f"ℹ️ {miembro.mention} ya tiene el rol {rol.mention}", ephemeral=True)
        return
    try:
        await miembro.add_roles(rol)
        await interaction.response.send_message(f"✅ Rol {rol.mention} asignado a {miembro.mention}")
        logger.info(f"🎭 {rol.name} asignado a {miembro.name} por {interaction.user.name}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error al asignar el rol: {e}", ephemeral=True)

@bot.tree.command(name="clear_spam", description="🧹 Limpiar el contador de spam")
@discord.app_commands.default_permissions(administrator=True)
async def slash_clear_spam(interaction: discord.Interaction):
    global spam_counter
    spam_counter.clear()
    await interaction.response.send_message("✅ Contador de spam limpiado.")
    logger.info(f"🧹 Contador de spam limpiado por {interaction.user.name}")

# =============================================
# COMANDOS CON PREFIJO (Mantenidos para compatibilidad)
# =============================================
@bot.command(name='panel')
async def panel_cmd(ctx):
    if not tiene_rol_permitido(ctx.author):
        await ctx.send("❌ No tienes permiso para usar este comando.")
        return
    await ctx.send("✅ El panel se envía automáticamente al canal configurado.")

@bot.command(name='clear_spam')
@commands.has_permissions(administrator=True)
async def clear_spam_cmd(ctx):
    global spam_counter
    spam_counter.clear()
    await ctx.send("✅ Contador de spam limpiado.")

@bot.command(name='set_autorole')
@commands.has_permissions(administrator=True)
async def set_autorole_cmd(ctx, rol_id: int = None):
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
async def add_autorole_cmd(ctx, miembro: discord.Member = None):
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
# INICIAR EL BOT
# =============================================
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")
