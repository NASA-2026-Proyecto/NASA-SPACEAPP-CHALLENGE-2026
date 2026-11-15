"""Sonificación: cada fenómeno, convertido en sonido a partir de su valor en un punto.

Un módulo por sonido (`air`, `rain`, `fire`), todos con las mismas tres piezas:

1. `mapping(valor)`: del dato a los parámetros del sonido. Todo cuelga de un solo número
   entre 0 y 1 (`intensity`), con reglas fijas: es una traducción del dato, no música.
2. `describe(muestra, parámetros)`: qué se oye y por qué, en palabras (lectores de pantalla).
3. `synthesize(muestra, parámetros, semilla)`: el audio. Es puro y determinista: el mismo
   punto, con los mismos datos y la misma semilla, suena siempre igual.

`dsp` tiene los bloques de síntesis (ruido, filtros, granos, reverberación, WAV) y
`common` lo que comparten los sonidos (la muestra de un punto, direcciones, textos).
Solo depende de numpy. De dónde sale la muestra (las escenas) es cosa de
`app.services.sonification`.
"""
