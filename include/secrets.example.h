#pragma once

// ============================================================
// Plantilla AWS IoT Core de SmartPark, sin credenciales reales.
// Pegar los PEM completos antes de implementar la conexion IoT.
// Los bloques vacios son marcadores, no certificados validos.
// ============================================================

#include <pgmspace.h>

// Amazon Root CA 1
static const char AWS_ROOT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----

-----END CERTIFICATE-----
)EOF";

// Certificado del dispositivo descargado al crear el Thing.
static const char AWS_DEVICE_CERT[] PROGMEM = R"CERT(
-----BEGIN CERTIFICATE-----

-----END CERTIFICATE-----
)CERT";

// Clave privada: conservar las cabeceras del PEM descargado.
// Si usa PKCS#8, las cabeceras son BEGIN/END PRIVATE KEY (sin RSA).
static const char AWS_PRIVATE_KEY[] PROGMEM = R"KEY(
-----BEGIN RSA PRIVATE KEY-----

-----END RSA PRIVATE KEY-----
)KEY";
