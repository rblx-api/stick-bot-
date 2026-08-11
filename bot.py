import os
import json
import discord
from discord import ui
from discord.ext import commands
import re
from collections import defaultdict
import aiohttp

# =============================================
# CONFIGURACIÓN
# =============================================
TOKEN = os.getenv('TOKEN')  # Token del bot de Discord
if not TOKEN:
    raise ValueError("❌ No se encontró el TOKEN. Configúralo en variables de entorno.")

GROQ_API_KEY = "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"  # API Key de Groq
CANAL_IA_ID = 1536862569497624606  # ID del canal donde la IA responderá

ROL_PERMITIDO_ID = 1519744694416965782      # Rol que puede warnear, banear y gestionar tickets
ROL_EXENTO_ID = 1519793995264294972         # Rol exento de moderación automática
CANAL_PANEL_ID = 1519029606684823732        # Canal donde se envía el panel de tickets
CANAL_BIENVENIDA = 1502668382640668853      # Canal de bienvenida
CANAL_DESPEDIDA  = 1502668463435419839      # Canal de despedida
CATEGORIA_TICKETS_ID = None                 # ID de categoría (opcional, si quieres fijar una)
ARCHIVO_WARNS = 'warns.json'                # Archivo para almacenar los warns

# =============================================
# INTENTS Y BOT
# =============================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Diccionario para tickets activos (se mantiene en memoria)
tickets_activos = {}

# Diccionario para control de spam (mensajes por usuario)
spam_counter = defaultdict(list)
SPAM_LIMIT = 5  # Número máximo de mensajes permitidos en un período
SPAM_TIME = 10  # Período de tiempo en segundos

# =============================================
# FUNCIONES PARA MANEJO DE WARNS (JSON)
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
# FUNCIONES DE MODERACIÓN
# =============================================
def contiene_link(texto):
    """Detecta si el mensaje contiene un enlace"""
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
    """Detecta si el mensaje contiene contenido NSFW"""
    palabras_nsfw = [
        'porno', 'xxx', 'nsfw', 'porn', 'porno', 'xxx',
        'chica', 'chicas', 'mujer', 'mujeres', 'desnuda',
        'desnudo', 'tetas', 'culo', 'cojer', 'coger',
        'sexo', 'sexual', 'porno', 'pornografía', 'pornografia',
        'culo', 'teta', 'pene', 'vagina'
    ]
    texto_lower = texto.lower()
    for palabra in palabras_nsfw:
        if palabra in texto_lower:
            return True
    return False

def contiene_palabras_prohibidas(texto):
    """Detecta si el mensaje contiene palabras prohibidas"""
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
    """Aplica un warn a un usuario y si tiene 3 warns lo banea"""
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
    """Verifica si el usuario tiene alguno de los roles exentos"""
    roles_exentos = [ROL_PERMITIDO_ID, ROL_EXENTO_ID]
    for rol_id in roles_exentos:
        if discord.utils.get(member.roles, id=rol_id):
            return True
    return False

# =============================================
# FUNCIÓN DE IA PARA GROQ
# =============================================
async def consultar_groq(pregunta):
    """Consulta la API de Groq para obtener una respuesta"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "mixtral-8x7b-32768",
        "messages": [
            {"role": "system", "content": "Eres un asistente útil y amigable. Responde de manera clara y concisa."},
            {"role": "user", "content": pregunta}
        ],
        "temperature": 0.7,
        "max_tokens": 500,
        "top_p": 0.9
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    resultado = await response.json()
                    respuesta = resultado['choices'][0]['message']['content']
                    return respuesta
                else:
                    error_text = await response.text()
                    print(f"❌ Error en la API de Groq: {response.status} - {error_text}")
                    return "❌ Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo más tarde."
    except Exception as e:
        print(f"❌ Error al consultar la API de Groq: {e}")
        return "❌ Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo más tarde."

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

# =============================================
# VISTA DESPUÉS DE CLAIM
# =============================================
class TicketButtonsAfterClaim(ui.View):
    def __init__(self, usuario_id, canal_id, quien_claimo):
        super().__init__(timeout=None)
        self.usuario_id = usuario_id
        self.canal_id = canal_id
        self.quien_claimo = quien_claimo

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

# =============================================
# EVENTO ON_READY
# =============================================
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'📡 IA responderá en el canal: {CANAL_IA_ID}')
    
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
# EVENTO DE BIENVENIDA
# =============================================
@bot.event
async def on_member_join(member):
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

    # =============================================
    # SISTEMA DE IA (SOLO EN CANAL ESPECÍFICO)
    # =============================================
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

    # =============================================
    # SISTEMA DE MODERACIÓN AUTOMÁTICA
    # =============================================
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
    # COMANDOS STICK (warn, unwarn, ban)
    # =============================================
    if message.content.lower().startswith('stick '):
        partes = message.content.split()
        if len(partes) >= 2:
            comando = partes[1].lower()
            
            if len(message.mentions) == 0:
                await message.channel.send("❌ Debes mencionar a un usuario: `stick warn/unwarn/ban @usuario`")
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
# COMANDO clear_spam
# =============================================
@bot.command(name='clear_spam')
@commands.has_permissions(administrator=True)
async def clear_spam(ctx):
    """Limpia el contador de spam de todos los usuarios"""
    global spam_counter
    spam_counter.clear()
    await ctx.send("✅ Contador de spam limpiado.")

# =============================================
# COMANDOS DE IA
# =============================================
@bot.command(name='test_ia')
async def test_ia(ctx):
    """Comando para probar que la IA funciona"""
    if ctx.channel.id != CANAL_IA_ID:
        await ctx.send("❌ Este comando solo funciona en el canal de IA.")
        return
    
    await ctx.send("🤖 Bot de IA funcionando correctamente. Etiquétame con @bot y haz tu pregunta.")

@bot.command(name='set_ia_channel')
@commands.has_permissions(administrator=True)
async def set_ia_channel(ctx, canal_id: int = None):
    """Cambia el canal donde la IA responde (solo admins)"""
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

# =============================================
# INICIAR EL BOT
# =============================================
if __name__ == "__main__":
    bot.run(TOKEN)
