def generar_intro(texto):
    template = f"""
-- Intro generada por Stick Hub
-- Versión simplificada para máxima compatibilidad

local Players = game:GetService("Players")
local player = Players.LocalPlayer
if not player then player = Players.PlayerAdded:Wait() end

local screenGui = Instance.new("ScreenGui")
screenGui.Name = "IntroGui"
screenGui.Parent = player:WaitForChild("PlayerGui")

-- Fondo
local background = Instance.new("Frame")
background.Size = UDim2.new(1, 0, 1, 0)
background.BackgroundColor3 = Color3.fromRGB(10, 5, 30)
background.BorderSizePixel = 0
background.Parent = screenGui

-- Texto de bienvenida
local title = Instance.new("TextLabel")
title.Size = UDim2.new(0, 400, 0, 80)
title.Position = UDim2.new(0.5, -200, 0.3, -40)
title.BackgroundTransparency = 1
title.Text = "{texto}"
title.TextColor3 = Color3.fromRGB(255, 255, 255)
title.TextSize = 36
title.TextFont = Enum.Font.GothamBold
title.TextXAlignment = Enum.TextXAlignment.Center
title.TextYAlignment = Enum.TextYAlignment.Center
title.Parent = screenGui
title.AnchorPoint = Vector2.new(0.5, 0.5)

-- Botón Continuar
local button = Instance.new("TextButton")
button.Size = UDim2.new(0, 200, 0, 50)
button.Position = UDim2.new(0.5, -100, 0.6, 0)
button.BackgroundColor3 = Color3.fromRGB(255, 70, 130)
button.BackgroundTransparency = 0.3
button.BorderSizePixel = 0
button.Text = "▶ CONTINUAR"
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.TextSize = 20
button.TextFont = Enum.Font.GothamBold
button.Parent = screenGui
button.AnchorPoint = Vector2.new(0.5, 0.5)

-- Cerrar la intro al hacer clic
button.MouseButton1Click:Connect(function()
    screenGui:Destroy()
end)

print("Intro generada por Stick Hub")
"""
    return template
