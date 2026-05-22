# OAG — Sistema de Auditorías Comerciales

Sistema para auditar distribuidores (DS) de Syngenta Argentina.

## Arquitectura

- **Backend**: FastAPI + PostgreSQL (Railway)
- **Frontend**: Electron + React (distribuible como .exe)
- **IA**: Claude Opus (Anthropic) para clasificación, normalización y justificaciones

## Pasos de auditoría

| Paso | Nombre | Descripción |
|------|--------|-------------|
| 1 | Cruce de BD | Bajada de gestión vs comprobantes emitidos (ARCA) |
| 2 | Análisis Producto Ventas | Rankings, muestreo, clasificación IA, tabla apertura |
| 3 | Cruce CRM | Agroquímicos Syngenta vs reporte CRM |
| 4 | Análisis Compras | Comprobantes recibidos, resumen por proveedor |
| 5 | Informe Ejecutivo | Excel con 3 anexos (top 90% compras, agroquímicos, CRM) |
| 6 | Informe con Glosario | Igual al 5 con nombres estandarizados por IA |

## Setup Backend (Railway)

1. Crear proyecto en Railway
2. Agregar PostgreSQL plugin
3. Agregar variables de entorno:
   - `DATABASE_URL` (automático desde PostgreSQL plugin)
   - `JWT_SECRET_KEY` (string aleatorio largo)
   - `ANTHROPIC_API_KEY` (de console.anthropic.com)
4. Deploy desde GitHub conectando el repo

## Setup Frontend (.exe)

```bash
cd frontend
npm install
npm run dev          # desarrollo
npm run dist:win     # compilar .exe
```

El .exe resultante estará en `frontend/release/`.

## Credenciales iniciales

Al primer deploy se crea automáticamente:
- Email: `admin@oag.com`
- Contraseña: `oag2024`

**Cambiar la contraseña en el primer ingreso.**

## Configuración del backend URL en el .exe

Por defecto el .exe apunta a la URL de Railway configurada en `src/main/index.ts`.
También se puede cambiar desde la app: el campo se guarda en `localStorage`.
