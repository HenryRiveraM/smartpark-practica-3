# PF-07 — Persistencia de vinculación del usuario

## 1. Descripción

Esta prueba funcional tiene como objetivo verificar que el sistema conserve la vinculación del usuario con la skill de Alexa, incluso después de cerrar y volver a abrir la aplicación.

## 2. Objetivo

Comprobar que el usuario permanezca vinculado al sistema sin necesidad de ingresar nuevamente un PIN cada vez que se vuelve a iniciar la skill de Alexa.

## 3. Procedimiento

1. Abrir la skill de Alexa del sistema de parqueo inteligente.
2. Verificar que el usuario se encuentre vinculado previamente.
3. Consultar el estado del sistema mediante el comando de voz correspondiente.
4. Cerrar la skill de Alexa.
5. Volver a abrir la skill utilizando el comando: «Alexa, abre parqueo inteligente».
6. Solicitar nuevamente el estado del sistema.
7. Verificar que Alexa permita realizar la consulta sin solicitar el ingreso de un nuevo PIN.

## 4. Resultado esperado

El sistema debe conservar la vinculación del usuario después de cerrar y volver a abrir la skill de Alexa.

Al solicitar nuevamente el estado del sistema, Alexa debe permitir realizar la consulta sin solicitar otro PIN, manteniendo la asociación previamente establecida.

## 5. Evidencias

Se deben adjuntar las evidencias que demuestren:

- La vinculación inicial del usuario.
- El cierre de la skill de Alexa.
- La reapertura de la skill.
- La consulta del estado sin solicitar nuevamente el PIN.

## 6. Resultado de la prueba

**Estado: PENDIENTE DE VALIDACIÓN.**

La prueba se considerará aprobada cuando se compruebe que el usuario continúa vinculado después de cerrar y volver a abrir la skill, pudiendo consultar el estado del sistema sin ingresar nuevamente un PIN.