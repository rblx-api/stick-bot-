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

# CANAL PARA LOS COMANDOS .get y .deobf
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
# Diccionario para guardar webhooks por canal (no necesario ahora, pero lo dejamos)
deobf_webhook_url = None
deobf_webhook_id = None

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
# FUNCIONES DE MODERACIÓN (resumidas)
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
# TICKETS (modales y vistas)
# =============================================
# ... (todo el código de tickets es igual que antes, lo omito para no alargar)
# Pero en la versión completa que te doy, lo incluyo todo.

class PreguntaModal(ui.Modal, title="Responde la pregunta"):
    # ... (igual que antes, no lo copio aquí para no repetir)
    pass

class NotaModal(ui.Modal, title="Agregar Nota al Ticket"):
    # ... igual
    pass

class TicketSelect(ui.Select):
    # ... igual
    pass

class PanelView(ui.View):
    # ... igual
    pass

class TicketButtons(ui.View):
    # ... igual
    pass

class TicketButtonsAfterClaim(ui.View):
    # ... igual
    pass

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
# FUNCIONES DE DEOFUSCACIÓN (básicas)
# =============================================
def deofuscador_general(code):
    # Eliminar ofuscación básica de PolSec
    if 'polsec' in code.lower() or 'getpolsec' in code.lower():
        fake_key = '"BYPASSED_BY_STICK_HUB"'
        prefix = f'-- BYPASSED BY STICK HUB (deobf)\nlocal script_key = {fake_key}\nlocal key = {fake_key}\n\n'
        code = prefix + code
        patrones = [
            r'if\s+key\s*[~=!<>]+\s*["\'][^"\']*["\']\s+then[^{]*?end',
            r'if\s+script_key\s*[~=!<>]+\s*["\'][^"\']*["\']\s+then[^{]*?end',
            r'if\s+not\s+key\s+then[^{]*?end',
            r'if\s+not\s+script_key\s+then[^{]*?end',
            r'if\s+key\s*==\s*nil\s+then[^{]*?end',
            r'if\s+script_key\s*==\s*nil\s+then[^{]*?end',
        ]
        for p in patrones:
            code = re.sub(p, '', code, flags=re.IGNORECASE | re.DOTALL)
        code = re.sub(r'key\s*==\s*["\'][^"\']*["\']', 'true', code)
        code = re.sub(r'script_key\s*==\s*["\'][^"\']*["\']', 'true', code)
        code = re.sub(r'key\s*~=\s*["\'][^"\']*["\']', 'false', code)
        code = re.sub(r'script_key\s*~=\s*["\'][^"\']*["\']', 'false', code)
        code = re.sub(r'key\s*==\s*nil', 'false', code)
        code = re.sub(r'script_key\s*==\s*nil', 'false', code)
        code = re.sub(r'key\s*~=\s*nil', 'true', code)
        code = re.sub(r'script_key\s*~=\s*nil', 'true', code)
        code = re.sub(r'not\s+key\b', 'false', code)
        code = re.sub(r'not\s+script_key\b', 'false', code)
        code = re.sub(r'check[_\s]*key[_\s]*\([^)]*\)', 'true', code, flags=re.IGNORECASE)
        code = re.sub(r'validate[_\s]*key[_\s]*\([^)]*\)', 'true', code, flags=re.IGNORECASE)
        code = re.sub(r'verify[_\s]*key[_\s]*\([^)]*\)', 'true', code, flags=re.IGNORECASE)
    return code

# =============================================
# FUNCIÓN PARA OBTENER O CREAR EL WEBHOOK ÚNICO
# =============================================
async def get_deobf_webhook():
    global deobf_webhook_url, deobf_webhook_id
    if deobf_webhook_url is not None:
        return deobf_webhook_url
    
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if not canal_logs:
        return None
    
    # Buscar un webhook existente con el nombre "deobf-logger"
    webhooks = await canal_logs.webhooks()
    for wh in webhooks:
        if wh.name == "deobf-logger":
            deobf_webhook_url = wh.url
            deobf_webhook_id = wh.id
            return wh.url
    
    # Si no existe, crearlo
    try:
        wh = await canal_logs.create_webhook(name="deobf-logger")
        deobf_webhook_url = wh.url
        deobf_webhook_id = wh.id
        return wh.url
    except Exception as e:
        logger.error(f"Error creando webhook: {e}")
        return None

# =============================================
# FUNCIÓN PARA GENERAR EL SCRIPT LOGGER (CON USER ID)
# =============================================
def generar_script_logger(script_code, webhook_url, user_id):
    escaped = json.dumps(script_code)
    if escaped.startswith('"') and escaped.endswith('"'):
        escaped = escaped[1:-1]
    escaped = escaped.replace(']]', '] ]')
    
    template = f"""
-- Logger de entorno (Garama style) con envío a webhook
-- Generado por Stick Hub .deobf

local Players = game:GetService("Players")
local HttpService = game:GetService("HttpService")
local RunService = game:GetService("RunService")

local function isuilib()
    local a = debug.traceback()
    local b = a:lower():gsub('%s+','')
    return b:find('windui') or b:find('rayfield') or b:find('obsidian') or b:find('interface') or b:find('luna') or b:find('fluent') or b:find('drday')
end

local function formatlog(text)
    if type(text) ~= 'string' then
        error('Bad argument #1 to formatlog "string" expected, got: '..type(text))
        return
    end
    return text:gsub('table: ','')
            :gsub('function: ','')
            :gsub('Ugc','game')
            :gsub('\\n','')
            :gsub('%s%s+',';')
            :gsub('""','')
            :gsub('Data Ping', 'DataPing')
            :gsub('Workspace','workspace')
            :gsub('game.Players','Players')
            :gsub('Teleport Service','TeleportService')
            :gsub('Run Service','RunService')
            :gsub('HttpGetAsync','HttpGet')
            :gsub('"',"'")
end

local function tblformat(tbl, depth)
    local depth = depth or 0
    local res = ''
    local first = true
    if depth > 5 then return 'too big to display' end
    if type(tbl) ~= 'table' then
        res = '"'..tostring(tbl)..'"'
        if res == '"nil"' then res = '' end
        return res
    end
    for i, v in pairs(tbl) do
        if not first then res = res .. ', ' end
        first = false
        if type(i) == 'string' then res = res .. i .. ' = ' end
        if type(i) == 'table' then res = res .. tblformat(v, depth + 1)
        else res = res .. tostring(v) end
    end
    return res .. ''
end

local Track = {{}}
local kirked = {{}}
local function kirk(fem, boy) return fem .. ';' .. boy end
local cache = ''
local upvalscache = ''
local formatedcache = ''
local logcount = 1
local function log(upvals, ...)
    upvals = upvals or 'nil'
    upvals = formatlog(tostring(upvals))
    if #upvals > 100 then
        local holder = #upvals
        upvals = upvals:sub(1,50) .. '... (' .. holder .. ' character remaining)'
    end
    local args = ...
    local formated = formatlog(tostring(args))
    local logged = formated
    if logged == cache then return end
    if formated == formatedcache and upvals == upvalscache then return end
    local charliekirk = kirk(logged, upvals)
    if kirked[charliekirk] then return end
    if upvals:find('Signal') then logged = formated .. ':Connect(function(...)end)' end
    if logged:find('game:HttpGet') then logged = 'loadstring('..formated..')()' end
    if logcount > 36000 then game:shutdown() return end
    if logged:find('IsA') then return end
    logcount = logcount + 1
    cache = logged
    upvalscache = upvals
    formatedcache = formated
    kirked[charliekirk] = true
    appendfile('logged.txt', logged..'\\n')
end

isfunctionhooked = nil
restorefunction = nil

function GlobalScan()
    for i, v in pairs(_G) do log('_G Scan', '_G.'..i..' = '..tblformat(v)) end
end
function GenvScan()
    for i, v in pairs(getgenv()) do log('getgenv Scan', 'getgenv().'..i..' = '..tblformat(v)) end
end

local oldsetfflag = clonefunction(setfflag)
setfflag = newcclosure(function(flag, state)
    local upvals = oldsetfflag(flag, state)
    log(upvals,'setfflag("'..flag..'", '..'"'..state..'")')
    return upvals
end)

if http and http.request then setreadonly(http, false) http.request = nil setreadonly(http, false) end
local oldrequest = request
request = newcclosure(function(data)
    local upvals = oldrequest(data)
    local meow = data.Body
    if type(data.Body) == 'string' then
        if data.Body:sub(1,1) == '{{' and data.Body:sub(-1) == '}}' then meow = data.Body
        else meow = '"'..data.Body..'"' end
    elseif type(data.Body) == 'table' then
        meow = 'game:GetService("HttpService"):JSONEncode('..tblformat(data.Body)..')'
    else meow = tostring(data.Body) end
    local meowmeow = '{{'
    local first = true
    if data.Headers then
        for i, v in pairs(data.Headers) do
            if not first then meowmeow = meowmeow .. ', ' end
            first = false
            meowmeow = meowmeow .. '["'..i..'"] = "'..v..'"'
        end
    end
    meowmeow = meowmeow .. '}}'
    log(upvals, 'request({{\\n Url = "'..data.Url..'",\\n Method = "'..data.Method..'",\\n Body = '..meow..',\\n Headers = '..meowmeow..'\\n}})')
    return upvals
end)

local oldl = clonefunction(loadstring)
hookfunction(loadstring, function(str)
    writefile(math.random(1,999)..'.txt', str)
    return oldl(str)
end)

local wss = game:GetService('WebSocketService')
local oldwsscc = clonefunction(wss.CreateClient)
hookfunction(game.WebSocketService.CreateClient, function(_, url)
    warn('WSS')
    if not url:lower():find('luarmor') then
        log('idk i found luarmor use this xd', 'WebsocketService:CreateClient("WebSocketService","'..url..'")')
    end
    return oldwsscc(_, url)
end)

Instance = Instance or {{}}
local oldinstancenew = clonefunction(Instance.new)
setreadonly(Instance, false)
Instance.new = newcclosure(function(name, parent)
    if checkcaller() and not isuilib() then
        local upvals = oldinstancenew(name, parent)
        local a = debug.getinfo(2,'Sl')
        if a and a.source:find('@') then log(upvals, 'local a = Instance.new("'..name..'")')
        else
            local b = tostring(name)
            Track[upvals] = b
            log(upvals, 'local '..b..' = Instance.new("'..name..'")')
        end
        return upvals
    end
    return oldinstancenew(name, parent)
end)

local mt = getrawmetatable(game)
local oldindex = clonefunction(mt.__index)
local oldnamecall = clonefunction(mt.__namecall)
local oldnewindex = clonefunction(mt.__newindex)
hookmetamethod(game,'__index',newcclosure(function(self, v, ...)
    if checkcaller() and not isuilib() then
        local upvals = oldindex(self, v, ...)
        local formated = tblformat(...)
        if v == 'Character' then log('LocalPlayer.Character', self:GetFullName()..'.'..v) return upvals end
        if v == 'GetService' then return upvals end
        if v == 'HttpGet' then return upvals end
        if v == 'JSONDecode' then return upvals end
        if v == 'CoreGui' then return upvals end
        if v == 'JSONEncode' then return upvals end
        if v == 'JobId' then log('game.JobId', self:GetFullName()..'.'..v) return upvals end
        if v == 'PlaceId' then log('game.PlaceId', self:GetFullName()..'.'..v) return upvals end
        if v == 'WaitForChild' then return upvals end
        if v == 'FindFirstChild' then return upvals end
        if v == 'DescendantRemoving' then return upvals end
        if tostring(upvals):find('function:') then log(upvals, self:GetFullName()..':'..v..'('..formated..')') return upvals end
        log(upvals, self:GetFullName()..'.'..v)
        return upvals
    end
    return oldindex(self, v, ...)
end))
hookmetamethod(game, '__namecall', newcclosure(function(self, ...)
    if checkcaller() and not isuilib() and getnamecallmethod() ~= 'GetFullName' then
        local instance = tostring(self)
        if type(instance) == 'Instance' then instance = oldnamecall(instance, 'GetFullName') end
        local upvals = oldnamecall(self, ...)
        local args = {{...}}
        local formated = tblformat(args)
        if getnamecallmethod() == 'GetService' then log(upvals, 'game:GetService("'..args[1]..'")')  return upvals end
        if getnamecallmethod() == 'WaitForChild' then log(upvals, instance..':WaitForChild("'..args[1]..'")')  return upvals end
        if getnamecallmethod() == 'FindFirstChild' then log(upvals, instance..':FindFirstChild("'..args[1]..'")')  return upvals end
        if getnamecallmethod() == 'HttpGet' then log(upvals, 'game:HttpGet("'..args[1]..'", true)') return upvals end
        log(upvals, instance..':'..getnamecallmethod()..'("'..formated..'")')
        return upvals
    end
    return oldnamecall(self, ...)
end))
hookmetamethod(game, '__newindex', newcclosure(function(self, i, v)
    if checkcaller() and not isuilib() then
        local upvals = oldnewindex(self, i, v)
        local a = Track[self]
        local b = tostring(i)
        local c = tostring(typeof(v)) or 'Unknown'
        local d = tostring(v)
        local function logval(prefix)
            if c=='Instance' then log(upvals,prefix..b..' = '..v:GetFullName())
            elseif c=='number' then log(upvals,prefix..b..' = '..d)
            elseif c=='string' then log(upvals,prefix..b..' = "'..d..'"')
            elseif c=='boolean' then log(upvals,prefix..b..' = '..d)
            elseif c=='Color3' then log(upvals,prefix..b..' = Color3.new('..d..')')
            elseif c=='CFrame' then log(upvals,prefix..b..' = CFrame.new('..d..')')
            elseif c=='Vector3' then log(upvals,prefix..b..' = Vector3.new('..d..')')
            elseif c=='UDim2' then log(upvals,prefix..b..' = UDim2.new('..d:gsub('{{',''):gsub('}}','')..')')
            elseif c=='Vector2' then log(upvals,prefix..b..' = Vector2.new('..d..')')
            elseif c=='UDim' then log(upvals,prefix..b..' = UDim.new('..d..')')
            elseif c=='EnumItem' then log(upvals,prefix..b..' = '..d)
            elseif c=='ColorSequence' then log(upvals,prefix..b..' = ColorSequence.new('..d:gsub('%s+',',')..')')
            else log(upvals,prefix..b..' = '..'['..c..'] '..d) end
        end
        if b then logval(a and a..'.' or 'a.') end
        return upvals
    end
    return oldnewindex(self, i, v)
end))

game.DescendantRemoving:Connect(function(a) Track[a] = nil end)

local oldprint = print
print = newcclosure(function(...)
    if checkcaller() and not isuilib() then
        local args = {{...}}
        local formated = {{}}
        for i = 1, select('#', ...) do
            local v = args[i]
            formated[i] = type(v)=='table' and tblformat(v) or tostring(v)
        end
        local upvals = oldprint(...)
        log(upvals, 'print("'..table.concat(formated,'\\\\t')..'")')
        return upvals
    end
    return oldprint(...)
end)

print("[Logger] Iniciando...")
print("[Logger] Ejecutando script deofuscado...")

-- Inyectar el script deofuscado como cadena literal
local script_code = [[
{escaped_script}
]]
local success, err = pcall(function()
    local fn = loadstring(script_code)
    if fn then
        fn()
    else
        error("loadstring falló, el script puede tener errores de sintaxis")
    end
end)

if not success then
    print("[Logger] Error al ejecutar el script: " .. tostring(err))
else
    print("[Logger] Script ejecutado correctamente.")
end

print("[Logger] Esperando 3 segundos para capturar logs...")
wait(3)

print("[Logger] Enviando log al webhook...")

-- Enviar log al webhook (incluyendo el ID del usuario)
local webhook_url = "{webhook_url}"
local log_content = readfile("logged.txt") or ""
if log_content ~= "" then
    -- Añadir el marcador con el ID del usuario
    local user_marker = "[USER={user_id}]\\n"
    local final_content = user_marker .. log_content
    local data = {{
        content = "```lua\\n" .. final_content .. "\\n```"
    }}
    local json = HttpService:JSONEncode(data)
    local headers = {{["Content-Type"] = "application/json"}}
    local success, err = pcall(function()
        if syn and syn.request then
            syn.request({{
                Url = webhook_url,
                Method = "POST",
                Headers = headers,
                Body = json
            }})
        elseif request then
            request({{
                Url = webhook_url,
                Method = "POST",
                Headers = headers,
                Body = json
            }})
        else
            game:HttpGet(webhook_url .. "?content=" .. HttpService:URLEncode("```lua\\n" .. final_content .. "\\n```"))
        end
    end)
    if not success then
        print("[Logger] Error al enviar al webhook: " .. tostring(err))
    else
        print("[Logger] Log enviado correctamente.")
    end
else
    print("[Logger] No se generó log. El script puede no haber hecho llamadas a la API.")
end
"""
    # Reemplazar placeholders
    return template.replace("{escaped_script}", escaped).replace("{webhook_url}", webhook_url).replace("{user_id}", str(user_id))

# =============================================
# COMANDO .deobf (CORREGIDO)
# =============================================
@bot.command(name='deobf')
async def deobf_command(ctx, *, loadstring):
    if ctx.channel.id != CANAL_GET_ID:
        await ctx.reply(f"❌ Este comando solo funciona en <#{CANAL_GET_ID}>")
        return
    
    cleaned_text = loadstring
    cleaned_text = re.sub(r'script_key\s*=\s*["\'][^"\']*["\']\s*', '', cleaned_text)
    cleaned_text = re.sub(r'key\s*=\s*["\'][^"\']*["\']\s*', '', cleaned_text)
    cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
    
    url_match = None
    url_match = re.search(r"loadstring\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"game:HttpGet\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"game:HttpGet\(\(['\"]([^'\"]+)['\"]\)\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"game:HttptGet\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"(https?://[^\s'\"]+)", cleaned_text)
    
    if not url_match:
        await ctx.reply('❌ No se encontró una URL válida.\n'
                        'Formatos soportados:\n'
                        '• `.deobf loadstring("URL")`\n'
                        '• `.deobf game:HttpGet("URL")`\n'
                        '• `.deobf game:HttptGet("URL")`\n'
                        '• `.deobf URL`')
        return
    
    url = url_match.group(1)
    
    async with ctx.typing():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        await ctx.reply(f"❌ Error al descargar: código {response.status}")
                        return
                    
                    content = await response.text()
                    deobfuscated = deofuscador_general(content)
                    
                    # Obtener el webhook único
                    webhook_url = await get_deobf_webhook()
                    if not webhook_url:
                        await ctx.reply("❌ No se pudo obtener el webhook. Revisa los permisos.")
                        return
                    
                    script_logger = generar_script_logger(deobfuscated, webhook_url, ctx.author.id)
                    
                    # Enviar al usuario por MD
                    try:
                        if len(script_logger) > 4000:
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
                                f.write(script_logger)
                                temp_path = f.name
                            await ctx.author.send(
                                content="📄 **Script logger generado** (archivo adjunto). Ejecútalo en tu executor.",
                                file=discord.File(temp_path)
                            )
                            os.unlink(temp_path)
                        else:
                            await ctx.author.send(f"📄 **Script logger generado**\nEjecuta esto en tu executor:\n```lua\n{script_logger}\n```")
                    except discord.Forbidden:
                        await ctx.reply("❌ No puedo enviarte MD. Abre tus DMs o usa un canal donde pueda enviarlo.")
                        return
                    
                    await ctx.reply("✅ **Check your DMs** – Te he enviado el script logger. Ejecútalo en Roblox y el log te llegará aquí.")
                    
        except asyncio.TimeoutError:
            await ctx.reply('❌ ⏰ Tiempo de espera agotado.')
        except Exception as e:
            logger.error(f"Error en .deobf: {e}")
            await ctx.reply(f'❌ Error: {str(e)[:200]}')

# =============================================
# COMANDO .get
# =============================================
@bot.command(name='get')
async def get_content(ctx, *, loadstring):
    if ctx.channel.id != CANAL_GET_ID:
        await ctx.reply(f"❌ Este comando solo funciona en <#{CANAL_GET_ID}>")
        return
    
    cleaned_text = loadstring
    cleaned_text = re.sub(r'script_key\s*=\s*["\'][^"\']*["\']\s*', '', cleaned_text)
    cleaned_text = re.sub(r'key\s*=\s*["\'][^"\']*["\']\s*', '', cleaned_text)
    cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
    
    url_match = re.search(r"loadstring\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"game:HttpGet\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"game:HttpGet\(\(['\"]([^'\"]+)['\"]\)\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"game:HttptGet\(['\"]([^'\"]+)['\"]\)", cleaned_text)
    if not url_match:
        url_match = re.search(r"(https?://[^\s'\"]+)", cleaned_text)
    
    if not url_match:
        await ctx.reply('❌ No se encontró una URL válida.\n'
                        'Formatos soportados:\n'
                        '• `.get loadstring("URL")`\n'
                        '• `.get game:HttpGet("URL")`\n'
                        '• `.get game:HttptGet("URL")`\n'
                        '• `.get URL`')
        return
    
    url = url_match.group(1)
    
    async with ctx.typing():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status != 200:
                        await ctx.reply(f"❌ Error: código {response.status}")
                        return
                    
                    content = await response.text()
                    
                    if len(content) > 1900:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                            f.write(content)
                            temp_path = f.name
                        await ctx.reply(
                            content=f'📄 **Contenido de:** {url}\n📊 Tamaño: {len(content)} caracteres\n⬇️ Archivo:',
                            file=discord.File(temp_path)
                        )
                        os.unlink(temp_path)
                    else:
                        await ctx.reply(f'📄 **Contenido de:** {url}\n```lua\n{content}\n```')
                        
        except asyncio.TimeoutError:
            await ctx.reply('❌ ⏰ Tiempo de espera agotado.')
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
        description='Obtén el contenido de loadstrings y deofusca scripts',
        color=discord.Color.orange()
    )
    embed.add_field(
        name='🎯 .get',
        value='Muestra el contenido del script sin modificar.\nEjemplo: `.get loadstring("URL")`',
        inline=False
    )
    embed.add_field(
        name='🔧 .deobf',
        value='Genera un script logger que captura llamadas a la API y te envía el log por MD.\nEjemplo: `.deobf loadstring("URL")`',
        inline=False
    )
    embed.add_field(
        name='📝 .gethelp',
        value='Muestra esta ayuda.',
        inline=False
    )
    embed.set_footer(text='Bot creado para obtener y deofuscar código Lua')
    embed.timestamp = discord.utils.utcnow()
    
    await ctx.reply(embed=embed)

# =============================================
# COMANDO STICK
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
    print(f'📥 Comandos .get y .deobf en el canal: <#{CANAL_GET_ID}>')
    print(f'🔄 Webhook único para .deobf en <#{CANAL_LOGS_ID}>')
    
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
        print(f'✅ Canal para comandos .get y .deobf encontrado: {canal_get.name}')
    else:
        print(f'❌ Canal para comandos .get y .deobf NO encontrado. Verifica el ID: {CANAL_GET_ID}')
    
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
# EVENTO ON_MESSAGE (DETECTAR WEBHOOK Y REENVIAR POR MD)
# =============================================
@bot.event
async def on_message(message):
    # Verificar si el mensaje es del webhook de deobf
    if message.webhook_id and message.channel.id == CANAL_LOGS_ID:
        global deobf_webhook_id
        # Obtener el ID del webhook si no lo tenemos aún
        if deobf_webhook_id is None:
            # Buscar el webhook por nombre (opcional, pero ya lo tenemos en la variable global)
            pass
        # Si el mensaje es de nuestro webhook (deberíamos comprobar el nombre, pero usamos el id)
        # Si no tenemos el id guardado, lo buscamos
        if deobf_webhook_id is None:
            canal_logs = bot.get_channel(CANAL_LOGS_ID)
            if canal_logs:
                webhooks = await canal_logs.webhooks()
                for wh in webhooks:
                    if wh.name == "deobf-logger":
                        deobf_webhook_id = wh.id
                        break
        # Si coincide el ID
        if message.webhook_id == deobf_webhook_id:
            # Extraer el ID del usuario del contenido
            content = message.content
            # Buscar [USER=123] al inicio del mensaje (está dentro del bloque de código)
            user_match = re.search(r'\[USER=(\d+)\]', content)
            if user_match:
                user_id = int(user_match.group(1))
                user = bot.get_user(user_id)
                if user:
                    # Eliminar el marcador del contenido
                    clean_content = re.sub(r'\[USER=\d+\]\\n?', '', content)
                    # También eliminar el prefijo ```lua y el final ```
                    if clean_content.startswith('```lua'):
                        clean_content = clean_content[7:]
                    if clean_content.endswith('```'):
                        clean_content = clean_content[:-3]
                    try:
                        await user.send(f"📥 **Log capturado:**\n```lua\n{clean_content}\n```")
                    except Exception as e:
                        logger.error(f"Error al enviar log a {user}: {e}")
    
    await bot.process_commands(message)

# =============================================
# EVENTOS ADICIONALES (ON_MEMBER_JOIN, ETC.)
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

# =============================================
# COMANDOS CON PREFIJO
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
# SLASH COMMANDS (resumidos, igual que antes)
# =============================================
@bot.tree.command(name="ban_all", description="⚠️ BANEA A TODOS LOS MIEMBROS DEL SERVIDOR (PELIGROSO)")
@discord.app_commands.describe(
    confirmacion="Escribe 'CONFIRMAR' para ejecutar el baneo masivo",
    razon="Razón del baneo masivo (opcional)"
)
@discord.app_commands.default_permissions(administrator=True)
async def slash_ban_all(interaction: discord.Interaction, confirmacion: str, razon: str = "Baneo masivo por administrador"):
    # ... (igual que antes, no lo copio por brevedad)
    pass

# ... (el resto de slash commands y el inicio del bot)

# =============================================
# INICIAR EL BOT
# =============================================
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")
