import os
import json
import discord
from discord import ui
from discord.ext import commands
import re
from collections import defaultdict
import asyncio

# =============================================
# CONFIGURACIÓN (cambia los valores según tu servidor)
# =============================================
TOKEN = os.getenv('TOKEN')  # o escribe tu token entre comillas
if not TOKEN:
    raise ValueError("❌ No se encontró el TOKEN. Configúralo en variables de entorno.")

ROL_PERMITIDO_ID = 1519744694416965782      # Rol que puede warnear, banear y gestionar tickets
ROL_EXENTO_ID = 1519793995264294972         # Rol exento de moderación automática
CANAL_PANEL_ID = 1519029606684823732        # Canal donde se envía el panel de tickets
CANAL_BIENVENIDA = 1502668382640668853      # Canal de bienvenida
CANAL_DESPEDIDA  = 1502668463435419839      # Canal de despedida
CANAL_INVITACIONES = 1503417211073859644    # Canal donde se envían las invitaciones
CATEGORIA_TICKETS_ID = None                 # ID de categoría (opcional, si quieres fijar una)
ARCHIVO_WARNS = 'warns.json'                # Archivo para almacenar los warns
ARCHIVO_INVITES = "invites_data.json"       # Archivo para almacenar las invitaciones

# =============================================
# INTENTS Y BOT
# =============================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Necesario para bienvenidas/despedidas
intents.invites = True  # Necesario para detectar invitaciones

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
# FUNCIONES PARA MANEJO DE INVITACIONES (JSON)
# =============================================
def cargar_invites():
    if os.path.exists(ARCHIVO_INVITES):
        with open(ARCHIVO_INVITES, "r", encoding='utf-8') as f:
            return json.load(f)
    return {}

def guardar_invites(datos):
    with open(ARCHIVO_INVITES, "w", encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)

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
        'sexo', 'sexual', 'porno', 'pornografía', 'pornografia'
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
    
    # Enviar mensaje de warn
    if canal:
        await canal.send(f"⚠️ {member.mention} ha recibido un warn por: {razon}. Total: {warns[user_id]}")
    
    # Si llega a 3 warnings, banear automáticamente
    if warns[user_id] >= 3:
        try:
            await member.ban(reason=f"3 warnings acumulados por {razon}")
            if canal:
                await canal.send(f"🚫 {member.mention} ha sido baneado por acumular 3 warnings.")
            # Eliminar warnings del usuario después del baneo
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
# MODAL PARA PREGUNTAR AL USUARIO (TICKETS) - CORREGIDO
# =============================================
class PreguntaModal(ui.Modal, title="Responde la pregunta"):
    def __init__(self, tipo_ticket, usuario):
        super().__init__()
        self.tipo_ticket = tipo_ticket
        self.usuario = usuario
        # Definir la pregunta según el tipo (label corto, placeholder largo)
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

            # Verificar si ya tiene un ticket abierto
            for channel_id, data in tickets_activos.items():
                if data['usuario_id'] == usuario.id and data['abierto']:
                    await interaction.followup.send("❌ Ya tienes un ticket abierto. Ciérralo antes de abrir otro.", ephemeral=True)
                    return

            # Crear canal de ticket
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

            # Guardar información del ticket
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
# SELECT DEL PANEL PRINCIPAL (sin Lagger)
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
# VISTA DEL PANEL (con el Select)
# =============================================
class PanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# =============================================
# BOTONES DE TICKET (Cerrar y Claim)
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

        # Marcar como cerrado antes de eliminar
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

        # Marcar como reclamado
        tickets_activos[self.canal_id]['claimado_por'] = interaction.user.id
        
        # Obtener el usuario que abrió el ticket
        usuario_id = tickets_activos[self.canal_id]['usuario_id']
        usuario = interaction.guild.get_member(usuario_id)

        # Actualizar la vista (quitar el botón de claim)
        nueva_vista = TicketButtonsAfterClaim(self.usuario_id, self.canal_id, interaction.user)
        await interaction.response.edit_message(view=nueva_vista)

        # Enviar mensaje al canal del ticket etiquetando al usuario que abrió el ticket
        canal = interaction.guild.get_channel(self.canal_id)
        if canal:
            embed = discord.Embed(
                title="📌 Ticket reclamado",
                description=f"**{usuario.mention if usuario else 'Usuario'}, tu ticket ha sido reclamado por {interaction.user.mention}**\n\nEl staff se encargará de tu caso.",
                color=discord.Color.green()
            )
            await canal.send(embed=embed)

# =============================================
# VISTA DESPUÉS DE CLAIM (sin el botón de claim)
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
# EVENTO ON_READY: enviar panel de tickets y mensaje de inicio
# =============================================
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    # Cargar datos de invitaciones
    global invites_data
    invites_data = cargar_invites()
    print(f"📊 Datos de invitaciones cargados: {len(invites_data)} usuarios registrados")
    
    # Enviar el panel al canal configurado
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
# EVENTO DE BIENVENIDA (con embed y miniatura)
# =============================================
@bot.event
async def on_member_join(member):
    # Enviar bienvenida
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
    # SISTEMA DE INVITACIONES (MEJORADO)
    # =============================================
    try:
        # Esperar un momento para que Discord registre la nueva invitación
        await discord.utils.sleep(2)
        
        # Obtener todas las invitaciones del servidor
        invites = await member.guild.invites()
        
        # Buscar al invitador usando audit logs
        invitador = None
        
        # Método 1: Usar audit logs para encontrar quién creó la invitación
        async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.invite_create):
            for invite in invites:
                if hasattr(entry.target, 'code') and entry.target.code == invite.code:
                    # Verificar si esta invitación tiene más usos que antes
                    if invite.uses > 0:
                        invitador = entry.user
                        break
            if invitador:
                break
        
        # Método 2: Si no se encontró, intentar con el método de conteo de usos
        if invitador is None:
            # Obtener las invitaciones antes (usando cache)
            invites_before = getattr(member.guild, '_invites_cache', None)
            
            if invites_before is not None:
                for invite in invites:
                    before = next((i for i in invites_before if i.code == invite.code), None)
                    if before is not None and invite.uses > before.uses:
                        invitador = invite.inviter
                        break
            
            # Guardar las invitaciones actuales para futuras comparaciones
            member.guild._invites_cache = invites
        
        # Si encontramos al invitador
        if invitador and invitador != member:  # No contar auto-invitaciones
            # Sumar una invitación al invitador
            global invites_data
            invitador_id = str(invitador.id)
            invites_data[invitador_id] = invites_data.get(invitador_id, 0) + 1
            guardar_invites(invites_data)
            
            # Enviar mensaje al canal de invitaciones
            canal_inv = bot.get_channel(CANAL_INVITACIONES)
            if canal_inv:
                embed = discord.Embed(
                    title="🎉 ¡Nuevo miembro invitado!",
                    description=(
                        f"{invitador.mention} **tienes {invites_data[invitador_id]} invitaciones**\n"
                        f"¡Sigue así! 🚀"
                    ),
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(
                    name="Nuevo miembro",
                    value=f"{member.mention} se ha unido al servidor",
                    inline=False
                )
                embed.set_footer(text=f"Total de invitaciones: {invites_data[invitador_id]}")
                await canal_inv.send(embed=embed)
        
        else:
            # Si no se encuentra invitador (quizás se unió por invitación del servidor)
            canal_inv = bot.get_channel(CANAL_INVITACIONES)
            if canal_inv:
                embed = discord.Embed(
                    description=f"{member.mention} se ha unido al servidor (invitación desconocida)",
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await canal_inv.send(embed=embed)
                
    except Exception as e:
        print(f"❌ Error al procesar la invitación: {e}")
        # Enviar un mensaje simple en caso de error
        canal_inv = bot.get_channel(CANAL_INVITACIONES)
        if canal_inv:
            embed = discord.Embed(
                description=f"{member.mention} se ha unido al servidor (error al detectar invitación)",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await canal_inv.send(embed=embed)

# =============================================
# EVENTO DE DESPEDIDA (con embed e imagen grande)
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
# EVENTO ON_MESSAGE: SISTEMA DE MODERACIÓN AUTOMÁTICA + COMANDOS
# =============================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Verificar si el usuario es exento de moderación
    if es_exento(message.author):
        await bot.process_commands(message)
        return

    # =============================================
    # SISTEMA DE MODERACIÓN AUTOMÁTICA
    # =============================================
    mensaje_borrado = False
    razon = None
    contenido = message.content

    # 1. Verificar links
    if contiene_link(contenido):
        razon = "No se permiten enlaces"
        mensaje_borrado = True

    # 2. Verificar NSFW
    elif contiene_nsfw(contenido):
        razon = "Contenido inapropiado (NSFW)"
        mensaje_borrado = True

    # 3. Verificar palabras prohibidas
    elif contiene_palabras_prohibidas(contenido):
        razon = "Palabras prohibidas (promoción no autorizada)"
        mensaje_borrado = True

    # 4. Verificar spam (mensajes repetidos)
    else:
        # Control de spam
        user_id = message.author.id
        current_time = message.created_at.timestamp()
        
        # Limpiar mensajes antiguos del contador
        spam_counter[user_id] = [t for t in spam_counter[user_id] if current_time - t < SPAM_TIME]
        
        # Añadir mensaje actual
        spam_counter[user_id].append(current_time)
        
        # Si el usuario supera el límite de mensajes
        if len(spam_counter[user_id]) > SPAM_LIMIT:
            razon = "Spam (más de 5 mensajes en 10 segundos)"
            mensaje_borrado = True

    # Si se detectó una violación
    if mensaje_borrado:
        try:
            # Borrar el mensaje
            await message.delete()
            
            # Aplicar warn al usuario
            await aplicar_warn(message.author, razon, message.channel)
            
            # Enviar mensaje de advertencia
            embed = discord.Embed(
                title="⚠️ Moderación Automática",
                description=f"**{message.author.mention}** tu mensaje ha sido eliminado por: **{razon}**",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed, delete_after=10)
            
        except Exception as e:
            print(f"❌ Error al aplicar moderación: {e}")
    
    # Solo procesar comandos si no es un mensaje de moderación o si es un comando
    await bot.process_commands(message)

# =============================================
# COMANDOS DE ADMINISTRACIÓN PARA MODERACIÓN
# =============================================
@bot.command(name="clear_spam")
@commands.has_permissions(administrator=True)
async def clear_spam(ctx):
    """Limpia el contador de spam de todos los usuarios"""
    global spam_counter
    spam_counter.clear()
    await ctx.send("✅ Contador de spam limpiado.")

# =============================================
# COMANDOS DE INVITACIONES
# =============================================
@bot.command(name="invites")
async def mostrar_invitaciones(ctx, miembro: discord.Member = None):
    """Comando para ver cuántas invitaciones tiene un usuario"""
    if miembro is None:
        miembro = ctx.author
    
    global invites_data
    invitaciones = invites_data.get(str(miembro.id), 0)
    
    embed = discord.Embed(
        title="📊 Estadísticas de invitaciones",
        description=f"{miembro.mention} tiene **{invitaciones}** invitaciones",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=miembro.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="ranking")
async def ranking_invitaciones(ctx):
    """Muestra el ranking de los mejores invitadores"""
    global invites_data
    if not invites_data:
        await ctx.send("❌ No hay datos de invitaciones aún.")
        return
    
    # Ordenar los usuarios por número de invitaciones (de mayor a menor)
    ranking = sorted(invites_data.items(), key=lambda x: x[1], reverse=True)
    
    # Crear el mensaje
    mensaje = "🏆 **Ranking de invitaciones**\n\n"
    for i, (user_id, count) in enumerate(ranking[:10], 1):  # Top 10
        try:
            usuario = await bot.fetch_user(int(user_id))
            mensaje += f"**#{i}** {usuario.mention} - {count} invitaciones\n"
        except:
            mensaje += f"**#{i}** Usuario desconocido - {count} invitaciones\n"
    
    await ctx.send(mensaje)

# =============================================
# COMANDOS DE ADMINISTRACIÓN PARA INVITACIONES
# =============================================
@bot.command(name="reset_invites")
@commands.has_permissions(administrator=True)
async def resetear_invitaciones(ctx, miembro: discord.Member):
    """Reinicia las invitaciones de un usuario (solo admins)"""
    global invites_data
    invites_data[str(miembro.id)] = 0
    guardar_invites(invites_data)
    await ctx.send(f"✅ Las invitaciones de {miembro.mention} han sido reiniciadas.")

@bot.command(name="add_invites")
@commands.has_permissions(administrator=True)
async def agregar_invitaciones(ctx, miembro: discord.Member, cantidad: int):
    """Añade invitaciones manualmente a un usuario (solo admins)"""
    global invites_data
    user_id = str(miembro.id)
    invites_data[user_id] = invites_data.get(user_id, 0) + cantidad
    guardar_invites(invites_data)
    await ctx.send(f"✅ Se añadieron {cantidad} invitaciones a {miembro.mention}. Total: {invites_data[user_id]}")

# =============================================
# COMANDO !panel (para reenviar el panel manualmente)
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
# INICIAR EL BOT
# =============================================
if __name__ == "__main__":
    bot.run(TOKEN)
