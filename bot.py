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

# ROLES PERMITIDOS
ROL_PERMITIDO_ID = 1519744694416965782
ROL_PERMITIDO_2_ID = 1498525987783053473
ROL_PERMITIDO_3_ID = 1502898587691122688
ROL_EXENTO_ID = 1519793995264294972
AUTO_ROLE_ID = 1508133051798917140

# Lista de todos los roles permitidos
ROLES_PERMITIDOS = [ROL_PERMITIDO_ID, ROL_PERMITIDO_2_ID, ROL_PERMITIDO_3_ID]

CANAL_PANEL_ID = 1519029606684823732
CANAL_BIENVENIDA = 1502668382640668853
CANAL_DESPEDIDA = 1502668463435419839
CATEGORIA_TICKETS_ID = 1536466416851488828
CANAL_SUGERENCIAS_ID = 1536466416851488828
CANAL_LOGS_ID = 1517328591732477962

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
# FUNCIÓN PARA VERIFICAR ROLES PERMITIDOS
# =============================================
def tiene_rol_permitido(member):
    """Verifica si el miembro tiene alguno de los roles permitidos"""
    for rol_id in ROLES_PERMITIDOS:
        if discord.utils.get(member.roles, id=rol_id):
            return True
    return False

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
    roles_exentos = [ROL_EXENTO_ID]
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
# MODAL PARA RAZÓN DEL TICKET
# =============================================
class TicketReasonModal(ui.Modal, title="📩 Abrir Ticket"):
    razon = ui.TextInput(
        label="¿Qué necesitas?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe lo que necesitas aquí...",
        required=True,
        max_length=1000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            razon = self.razon.value
            guild = interaction.guild
            usuario = interaction.user

            # Verificar si ya tiene un ticket abierto
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
            
            # Agregar todos los roles permitidos al ticket
            for rol_id in ROLES_PERMITIDOS:
                rol = guild.get_role(rol_id)
                if rol:
                    overwrites[rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            canal = await categoria.create_text_channel(nombre_canal, overwrites=overwrites)

            tickets_activos[canal.id] = {
                'usuario_id': usuario.id,
                'razon': razon,
                'abierto': True,
                'claimado_por': None,
                'canal': canal
            }

            embed = discord.Embed(
                title=f"📩 Ticket de {usuario.name}",
                description=f"**Necesita:**\n{razon}\n\n*Un miembro del staff te atenderá en breve.*",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"ID: {canal.id} | Abierto por {usuario.name}")

            view = TicketButtons(usuario.id, canal.id)
            
            # Mencionar todos los roles permitidos
            mentions = " ".join([f"<@&{rol_id}>" for rol_id in ROLES_PERMITIDOS if guild.get_role(rol_id)])
            
            await canal.send(
                f"{usuario.mention} {mentions}",
                embed=embed,
                view=view
            )

            await interaction.followup.send(f"✅ Ticket creado: {canal.mention}", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error al crear el ticket: {str(e)}", ephemeral=True)

# =============================================
# MODAL PARA NOTAS INTERNAS
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
# VISTA DEL PANEL CON BOTÓN "OPEN TICKET"
# =============================================
class PanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="🔴 OPEN TICKET", style=discord.ButtonStyle.danger, custom_id="open_ticket_button")
    async def open_ticket_button(self, interaction: discord.Interaction, button: ui.Button):
        """Abre el modal para solicitar la razón del ticket"""
        await interaction.response.send_modal(TicketReasonModal())

# =============================================
# VISTAS DE TICKETS
# =============================================
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
                color=discord.Color.green()
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
# FUNCIÓN PARA ENVIAR EL PANEL (REUTILIZABLE)
# =============================================
async def enviar_panel(canal):
    """Función para enviar el panel de tickets a un canal"""
    try:
        # Limpiar mensajes antiguos del bot
        async for msg in canal.history(limit=100):
            if msg.author == bot.user:
                await msg.delete()
    except:
        pass
    
    # Panel simplificado con solo el texto "¿Necesitas ayuda? Abre un ticket y dinos qué necesitas"
    embed = discord.Embed(
        description=(
            "🔴🔴🔴 **¿NECESITAS AYUDA?** 🔴🔴🔴\n\n"
            "**Abre un ticket y dinos qué necesitas.**\n\n"
            "Presiona el botón **OPEN TICKET** y describe tu solicitud.\n"
            "Un miembro del staff te atenderá lo antes posible."
        ),
        color=discord.Color.red()
    )
    embed.set_footer(text="Presiona el botón 'OPEN TICKET' para abrir un ticket.")
    view = PanelView()
    await canal.send(embed=embed, view=view)
    print(f"✅ Panel enviado a {canal.name}")

# =============================================
# FUNCIÓN PARA BANEAR A TODOS (REUTILIZABLE)
# =============================================
async def ban_all_members(guild, author, razon="Baneo masivo"):
    """Función para banear a todos los miembros del servidor"""
    
    # Obtener todos los miembros (excepto el bot, dueño, admin y el que ejecuta)
    miembros_a_bannear = []
    miembros_omitidos = []
    
    for member in guild.members:
        # No banear al bot
        if member.id == bot.user.id:
            miembros_omitidos.append(f"🤖 {member.name} (Bot)")
            continue
        
        # No banear al dueño del servidor
        if member.id == guild.owner_id:
            miembros_omitidos.append(f"👑 {member.name} (Dueño)")
            continue
        
        # No banear al usuario que ejecuta el comando
        if member.id == author.id:
            miembros_omitidos.append(f"👤 {member.name} (Tú)")
            continue
        
        # No banear a administradores (por seguridad)
        if member.guild_permissions.administrator:
            miembros_omitidos.append(f"🛡️ {member.name} (Admin)")
            continue
        
        # No banear a usuarios con roles permitidos
        if tiene_rol_permitido(member):
            miembros_omitidos.append(f"🔰 {member.name} (Staff)")
            continue
        
        miembros_a_bannear.append(member)
    
    # Si no hay miembros para banear
    if not miembros_a_bannear:
        return {
            'baneados': 0,
            'errores': 0,
            'omitidos': miembros_omitidos,
            'errores_lista': []
        }
    
    # Ejecutar el baneo
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
    print(f'📌 Canal del panel: {CANAL_PANEL_ID}')
    
    await cargar_mutes()
    print(f'✅ Mutes cargados correctamente')
    
    # Sincronizar slash commands
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
    
    # Enviar el panel al canal especificado
    canal_panel = bot.get_channel(CANAL_PANEL_ID)
    if canal_panel:
        await enviar_panel(canal_panel)
    else:
        print(f'❌ Canal de panel NO encontrado. Verifica el ID: {CANAL_PANEL_ID}')

# =============================================
# COMANDO PARA ENVIAR EL PANEL MANUALMENTE
# =============================================
@bot.command(name='enviar_panel')
@commands.has_permissions(administrator=True)
async def enviar_panel_cmd(ctx):
    """Envía el panel de tickets al canal actual (SOLO ADMIN)"""
    await enviar_panel(ctx.channel)
    await ctx.send("✅ Panel enviado a este canal.", delete_after=5)

@bot.command(name='panel')
async def panel_cmd(ctx):
    if not tiene_rol_permitido(ctx.author):
        await ctx.send("❌ No tienes permiso para usar este comando.")
        return
    canal_panel = bot.get_channel(CANAL_PANEL_ID)
    if canal_panel:
        await enviar_panel(canal_panel)
        await ctx.send(f"✅ Panel enviado a {canal_panel.mention}")
    else:
        await ctx.send("❌ Canal de panel no encontrado.")

# =============================================
# RESTO DEL CÓDIGO (eventos, comandos, etc.)
# =============================================

# =============================================
# EVENTO DE BIENVENIDA + AUTO-ROLE + ANTI-RAID
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
# EVENTO DE LOGS - MENSAJES ELIMINADOS
# =============================================
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    
    if not message.guild:
        return
    
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    
    embed = discord.Embed(
        title="🗑️ Mensaje Eliminado",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
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

# =============================================
# EVENTO DE LOGS - MENSAJES EDITADOS
# =============================================
@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    
    if not before.guild:
        return
    
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    
    embed = discord.Embed(
        title="✏️ Mensaje Editado",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
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

# =============================================
# EVENTO DE LOGS - BANEOS
# =============================================
@bot.event
async def on_member_ban(guild, user):
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    
    embed = discord.Embed(
        title="🔨 Usuario Baneado",
        color=discord.Color.dark_red(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Usuario", value=f"{user.name}#{user.discriminator}", inline=True)
    embed.add_field(name="ID", value=user.id, inline=True)
    
    try:
        await canal_logs.send(embed=embed)
    except Exception as e:
        print(f"❌ Error al enviar log de ban: {e}")

# =============================================
# EVENTO DE LOGS - DESBANEOS
# =============================================
@bot.event
async def on_member_unban(guild, user):
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return
    
    embed = discord.Embed(
        title="✅ Usuario Desbaneado",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Usuario", value=f"{user.name}#{user.discriminator}", inline=True)
    embed.add_field(name="ID", value=user.id, inline=True)
    
    try:
        await canal_logs.send(embed=embed)
    except Exception as e:
        print(f"❌ Error al enviar log de unban: {e}")

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

    # =============================================
    # COMANDOS STICK
    # =============================================
    if message.content.lower().startswith('stick '):
        partes = message.content.split()
        if len(partes) >= 2:
            comando = partes[1].lower()
            
            # Verificar si tiene alguno de los roles permitidos
            if not tiene_rol_permitido(message.author):
                await message.channel.send("❌ No tienes el rol necesario para usar este comando.")
                await bot.process_commands(message)
                return

            # =============================================
            # COMANDO: stick ban all
            # =============================================
            if comando == 'ban' and len(partes) >= 3 and partes[2].lower() == 'all':
                # Verificar permisos del bot
                if not message.guild.me.guild_permissions.ban_members:
                    await message.channel.send("❌ El bot no tiene permisos para banear miembros.")
                    await bot.process_commands(message)
                    return
                
                # Pedir confirmación
                confirmacion_msg = await message.channel.send(
                    f"⚠️ **¿ESTÁS SEGURO?**\n"
                    f"Esto baneará a **TODOS** los miembros del servidor.\n"
                    f"Esta acción es **IRREVERSIBLE**.\n\n"
                    f"Para confirmar, escribe `stick confirmar ban all` en los próximos 30 segundos."
                )
                
                # Esperar confirmación
                def check(m):
                    return m.author == message.author and m.content.lower() == 'stick confirmar ban all' and m.channel == message.channel
                
                try:
                    await bot.wait_for('message', timeout=30.0, check=check)
                except asyncio.TimeoutError:
                    await message.channel.send("❌ Tiempo de confirmación agotado. Baneo cancelado.")
                    await bot.process_commands(message)
                    return
                
                # Ejecutar baneo masivo
                resultado = await ban_all_members(message.guild, message.author, "Baneo masivo por comando stick")
                
                # Enviar resultado
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
                
                await message.channel.send(embed=embed)
                
                # Log en canal de logs
                canal_logs = bot.get_channel(CANAL_LOGS_ID)
                if canal_logs:
                    log_embed = discord.Embed(
                        title="🔨 BANEO MASIVO POR STICK",
                        description=f"**Usuario:** {message.author.mention}\n"
                                    f"**Baneados:** {resultado['baneados']}\n"
                                    f"**Errores:** {resultado['errores']}",
                        color=discord.Color.red(),
                        timestamp=datetime.now()
                    )
                    await canal_logs.send(embed=log_embed)
                
                logger.info(f"🔨 Baneo masivo por stick ejecutado por {message.author.name}: {resultado['baneados']} baneados")
                
                await bot.process_commands(message)
                return

            # =============================================
            # COMANDOS STICK NORMALES
            # =============================================
            if len(message.mentions) == 0:
                await message.channel.send("❌ Debes mencionar a un usuario: `stick warn/unwarn/ban/mute/unmute @usuario`")
                await bot.process_commands(message)
                return

            user = message.mentions[0]

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
                razon = ' '.join(partes[3:]) if len(partes) > 3 else "Sin razón"
                
                match = re.match(r'(\d+)([smhd])', tiempo.lower())
                if not match:
                    await message.channel.send("❌ Formato inválido. Usa: 5m, 1h, 1d")
                    await bot.process_commands(message)
                    return
                
                cantidad, unidad = match.groups()
                cantidad = int(cantidad)
                
                segundos = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}.get(unidad, 0)
                total_segundos = cantidad * segundos
                
                if total_segundos > 86400 * 7:
                    await message.channel.send("❌ No puedes mutear por más de 7 días.")
                    await bot.process_commands(message)
                    return
                
                mute_role = await get_mute_role(message.guild)
                await user.add_roles(mute_role)
                
                end_time = datetime.now().timestamp() + total_segundos
                await guardar_mute(message.guild.id, user.id, end_time)
                mutes_activos[f"{message.guild.id}_{user.id}"] = end_time
                
                await message.channel.send(f"🔇 {user.mention} muteado por {cantidad}{unidad}. Razón: {razon}")
                
                async def desmutear():
                    await asyncio.sleep(total_segundos)
                    try:
                        await user.remove_roles(mute_role)
                        await eliminar_mute(message.guild.id, user.id)
                        if f"{message.guild.id}_{user.id}" in mutes_activos:
                            del mutes_activos[f"{message.guild.id}_{user.id}"]
                        await message.channel.send(f"🔊 {user.mention} ha sido desmuteado automáticamente")
                    except Exception as e:
                        print(f"Error al desmutear: {e}")
                
                bot.loop.create_task(desmutear())

            elif comando == 'unmute':
                mute_role = await get_mute_role(message.guild)
                if mute_role in user.roles:
                    await user.remove_roles(mute_role)
                    await eliminar_mute(message.guild.id, user.id)
                    if f"{message.guild.id}_{user.id}" in mutes_activos:
                        del mutes_activos[f"{message.guild.id}_{user.id}"]
                    await message.channel.send(f"🔊 {user.mention} ha sido desmuteado")
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
                except Exception as e:
                    await message.channel.send(f"❌ Error al banear: {e}")

    await bot.process_commands(message)

# =============================================
# SLASH COMMANDS (COMANDOS /)
# =============================================

# =============================================
# /ban_all - BANEAR A TODOS
# =============================================
@bot.tree.command(name="ban_all", description="⚠️ BANEA A TODOS LOS MIEMBROS DEL SERVIDOR (PELIGROSO)")
@discord.app_commands.describe(
    confirmacion="Escribe 'CONFIRMAR' para ejecutar el baneo masivo",
    razon="Razón del baneo masivo (opcional)"
)
@discord.app_commands.default_permissions(administrator=True)
async def slash_ban_all(interaction: discord.Interaction, confirmacion: str, razon: str = "Baneo masivo por administrador"):
    """⚠️ BANEA A TODOS LOS MIEMBROS DEL SERVIDOR (SOLO ADMIN)"""
    
    # Verificar que el usuario tenga permisos de administrador
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
        return
    
    # Verificar que el bot tenga permisos para banear
    if not interaction.guild.me.guild_permissions.ban_members:
        await interaction.response.send_message("❌ El bot no tiene permisos para banear miembros.", ephemeral=True)
        return
    
    # Verificar confirmación
    if confirmacion.upper() != "CONFIRMAR":
        await interaction.response.send_message(
            "❌ Debes escribir `CONFIRMAR` para ejecutar el baneo masivo.\n"
            "⚠️ Este comando es **IRREVERSIBLE** y baneará a **TODOS** los miembros del servidor.",
            ephemeral=True
        )
        return
    
    # Ejecutar baneo masivo
    resultado = await ban_all_members(interaction.guild, interaction.user, razon)
    
    # Verificar si hay miembros para banear
    if resultado['baneados'] == 0 and resultado['errores'] == 0:
        await interaction.response.send_message(
            f"ℹ️ No hay miembros disponibles para banear.\n"
            f"Miembros omitidos: {len(resultado['omitidos'])}",
            ephemeral=True
        )
        return
    
    # Enviar resultado
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
    
    # Log en canal de logs
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

# =============================================
# OTROS SLASH COMMANDS
# =============================================

@bot.tree.command(name="blacklist", description="🚫 Agregar o quitar usuarios de la blacklist")
@discord.app_commands.describe(
    accion="Acción a realizar (add o remove)",
    usuario="Usuario a agregar o quitar de la blacklist"
)
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
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Encuesta creada por {interaction.user.name} | {datetime.now().strftime('%d/%m/%Y')}")
    
    await interaction.response.send_message(embed=embed)
    mensaje = await interaction.original_response()
    
    for i in range(min(len(opciones), 10)):
        await mensaje.add_reaction(emojis[i])
    
    logger.info(f"📊 Encuesta creada por {interaction.user.name}: {pregunta}")

@bot.tree.command(name="remind", description="⏰ Crear un recordatorio")
@discord.app_commands.describe(
    tiempo="Tiempo (ej: 10s, 5m, 1h, 1d)",
    recordatorio="Lo que quieres recordar"
)
async def slash_remind(interaction: discord.Interaction, tiempo: str, recordatorio: str):
    match = re.match(r'(\d+)([smhd])', tiempo.lower())
    if not match:
        await interaction.response.send_message("❌ Formato inválido. Usa: 10s, 5m, 1h, 1d", ephemeral=True)
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
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="ℹ️ Ver información de un usuario")
@discord.app_commands.describe(miembro="Usuario para ver su información (opcional)")
async def slash_userinfo(interaction: discord.Interaction, miembro: discord.Member = None):
    if miembro is None:
        miembro = interaction.user
    
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
# COMANDOS CON PREFIJO
# =============================================
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
