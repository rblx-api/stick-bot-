import os
import discord
from discord.ext import commands
import aiohttp
import asyncio
import json

# =============================================
# CONFIGURACIÓN
# =============================================
TOKEN = os.getenv('TOKEN')  # Token del bot de Discord
GROQ_API_KEY = "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"  # API Key de Groq
CANAL_IA_ID = 1536862569497624606  # ID del canal donde la IA responderá

# =============================================
# INTENTS Y BOT
# =============================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# =============================================
# FUNCIÓN PARA CONSULTAR LA API DE GROQ
# =============================================
async def consultar_groq(pregunta):
    """Consulta la API de Groq para obtener una respuesta"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "mixtral-8x7b-32768",  # Puedes cambiar el modelo
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
# EVENTO ON_READY
# =============================================
@bot.event
async def on_ready():
    print(f'✅ Bot de IA conectado como {bot.user}')
    print(f'📡 Responderá en el canal: {CANAL_IA_ID}')

# =============================================
# EVENTO ON_MESSAGE PARA IA
# =============================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # Verificar si el mensaje es en el canal correcto
    if message.channel.id != CANAL_IA_ID:
        return
    
    # Verificar si el bot fue mencionado
    if not bot.user.mentioned_in(message):
        return
    
    # Eliminar la mención del bot para obtener la pregunta real
    contenido = message.content
    for mention in message.mentions:
        if mention.id == bot.user.id:
            contenido = contenido.replace(f'<@{mention.id}>', '').replace(f'<@!{mention.id}>', '').strip()
    
    # Si no hay contenido después de la mención
    if not contenido:
        await message.reply("❓ ¿Qué necesitas saber? Hazme una pregunta.")
        return
    
    # Enviar indicador de que está procesando
    thinking_message = await message.reply("🤔 Pensando...")
    
    # Obtener respuesta de la IA
    respuesta = await consultar_groq(contenido)
    
    # Limitar la respuesta a 2000 caracteres (límite de Discord)
    if len(respuesta) > 1900:
        respuesta = respuesta[:1900] + "..."
    
    # Editar el mensaje con la respuesta
    try:
        await thinking_message.edit(content=respuesta)
    except Exception as e:
        await thinking_message.edit(content=f"❌ Error al mostrar la respuesta: {e}")

# =============================================
# COMANDO DE PRUEBA
# =============================================
@bot.command(name='test_ia')
async def test_ia(ctx):
    """Comando para probar que la IA funciona"""
    if ctx.channel.id != CANAL_IA_ID:
        await ctx.send("❌ Este comando solo funciona en el canal de IA.")
        return
    
    await ctx.send("🤖 Bot de IA funcionando correctamente. Etiquétame con @bot y haz tu pregunta.")

# =============================================
# COMANDO DE CONFIGURACIÓN (SOLO ADMIN)
# =============================================
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
