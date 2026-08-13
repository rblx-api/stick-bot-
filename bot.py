# =============================================
# COMANDO /ban_all - BANEAR A TODOS (CON SEGURIDAD)
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
    
    # Obtener todos los miembros (excepto el bot y el dueño)
    miembros_a_bannear = []
    miembros_omitidos = []
    
    for member in interaction.guild.members:
        # No banear al bot
        if member.id == interaction.client.user.id:
            miembros_omitidos.append(f"🤖 {member.name} (Bot)")
            continue
        
        # No banear al dueño del servidor
        if member.id == interaction.guild.owner_id:
            miembros_omitidos.append(f"👑 {member.name} (Dueño)")
            continue
        
        # No banear al usuario que ejecuta el comando
        if member.id == interaction.user.id:
            miembros_omitidos.append(f"👤 {member.name} (Tú)")
            continue
        
        # No banear a administradores (por seguridad)
        if member.guild_permissions.administrator:
            miembros_omitidos.append(f"🛡️ {member.name} (Admin)")
            continue
        
        miembros_a_bannear.append(member)
    
    # Verificar si hay miembros para banear
    if not miembros_a_bannear:
        await interaction.response.send_message(
            "ℹ️ No hay miembros disponibles para banear.\n"
            f"Miembros omitidos: {len(miembros_omitidos)}",
            ephemeral=True
        )
        return
    
    # Enviar mensaje de advertencia
    embed = discord.Embed(
        title="⚠️ ⚠️ ⚠️ BANEO MASIVO ⚠️ ⚠️ ⚠️",
        description=f"**Se van a banear {len(miembros_a_bannear)} miembros**\n\n"
                    f"Esta acción es **IRREVERSIBLE**.\n"
                    f"Los miembros baneados no podrán volver a unirse.\n\n"
                    f"**Razón:** {razon}\n\n"
                    f"⏳ El proceso puede tomar varios minutos...",
        color=discord.Color.red()
    )
    embed.add_field(
        name="Miembros omitidos",
        value="\n".join(miembros_omitidos[:10]) + (f"\n... y {len(miembros_omitidos) - 10} más" if len(miembros_omitidos) > 10 else ""),
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)
    
    # Enviar mensaje de inicio al canal de logs
    canal_logs = bot.get_channel(CANAL_LOGS_ID)
    if canal_logs:
        log_embed = discord.Embed(
            title="🔨 INICIANDO BANEO MASIVO",
            description=f"**Usuario:** {interaction.user.mention}\n"
                        f"**Miembros a banear:** {len(miembros_a_bannear)}\n"
                        f"**Razón:** {razon}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        await canal_logs.send(embed=log_embed)
    
    # Ejecutar el baneo
    baneados = 0
    errores = 0
    errores_lista = []
    
    # Crear barra de progreso
    mensaje_progreso = await interaction.followup.send(
        f"🔄 Baneando miembros... 0/{len(miembros_a_bannear)}"
    )
    
    for i, member in enumerate(miembros_a_bannear):
        try:
            await member.ban(reason=f"Baneo masivo por {interaction.user.name}: {razon}")
            baneados += 1
        except Exception as e:
            errores += 1
            errores_lista.append(f"{member.name}: {str(e)[:50]}")
        
        # Actualizar progreso cada 10 miembros
        if i % 10 == 0 or i == len(miembros_a_bannear) - 1:
            try:
                await mensaje_progreso.edit(
                    content=f"🔄 Baneando miembros... {i+1}/{len(miembros_a_bannear)} "
                            f"(✅ {baneados} baneados | ❌ {errores} errores)"
                )
            except:
                pass
    
    # Mensaje final
    embed_final = discord.Embed(
        title="✅ BANEO MASIVO COMPLETADO",
        description=f"**Total de miembros baneados:** {baneados}\n"
                    f"**Errores:** {errores}\n"
                    f"**Miembros omitidos:** {len(miembros_omitidos)}\n"
                    f"**Razón:** {razon}",
        color=discord.Color.green() if errores == 0 else discord.Color.orange()
    )
    
    if errores_lista:
        embed_final.add_field(
            name="Errores",
            value="\n".join(errores_lista[:10]) + (f"\n... y {len(errores_lista) - 10} más" if len(errores_lista) > 10 else ""),
            inline=False
        )
    
    await mensaje_progreso.edit(content=None, embed=embed_final)
    
    # Enviar log final al canal de logs
    if canal_logs:
        log_final = discord.Embed(
            title="✅ BANEO MASIVO FINALIZADO",
            description=f"**Usuario:** {interaction.user.mention}\n"
                        f"**Baneados:** {baneados}\n"
                        f"**Errores:** {errores}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        await canal_logs.send(embed=log_final)
    
    logger.info(f"🔨 Baneo masivo ejecutado por {interaction.user.name}: {baneados} baneados, {errores} errores")
