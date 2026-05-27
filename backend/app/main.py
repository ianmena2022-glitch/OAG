import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from .core.config import settings
from .core.database import engine, Base
from .models import user, expediente  # noqa: F401 — importar para crear tablas
from .api.routes import auth, expedientes, admin, pasos

# Crear tablas
Base.metadata.create_all(bind=engine)

# Crear directorio de uploads
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(expedientes.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(pasos.router, prefix="/api")


GITHUB_RELEASE_URL = (
    "https://github.com/ianmena2022-glitch/OAG/releases/latest/download/"
    "OGSA.Auditorias.Setup.1.0.0.exe"
)

LANDING_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>OGSA — Sistema de Auditorías Comerciales</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #F5F6F8;
      color: #1A1A2E;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* NAV */
    nav {
      background: #1C2B3A;
      padding: 0 40px;
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 3px solid #C8A84B;
    }
    .nav-brand { display: flex; align-items: center; gap: 12px; }
    .nav-logo {
      background: #1A4A8A;
      color: white;
      font-weight: 700;
      font-size: 13px;
      width: 36px; height: 36px;
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
    }
    .nav-name { color: #B0C4DE; font-size: 13px; font-weight: 500; letter-spacing: 0.3px; }
    .nav-badge {
      background: #2D7A4F;
      color: white;
      font-size: 10px;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 20px;
      letter-spacing: 0.5px;
    }

    /* HERO */
    .hero {
      background: linear-gradient(135deg, #1C2B3A 0%, #1A3A5C 100%);
      color: white;
      padding: 80px 40px 70px;
      text-align: center;
      position: relative;
      overflow: hidden;
    }
    .hero::before {
      content: '';
      position: absolute;
      top: -60px; right: -60px;
      width: 300px; height: 300px;
      background: rgba(26, 74, 138, 0.25);
      border-radius: 50%;
    }
    .hero::after {
      content: '';
      position: absolute;
      bottom: -80px; left: -40px;
      width: 250px; height: 250px;
      background: rgba(26, 74, 138, 0.15);
      border-radius: 50%;
    }
    .hero-inner { position: relative; z-index: 1; max-width: 680px; margin: 0 auto; }
    .hero-eyebrow {
      color: #7FB3E8;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 2px;
      text-transform: uppercase;
      margin-bottom: 16px;
    }
    .hero h1 {
      font-size: 42px;
      font-weight: 700;
      line-height: 1.15;
      margin-bottom: 20px;
      letter-spacing: -0.5px;
    }
    .hero h1 span { color: #7FB3E8; }
    .hero p {
      font-size: 16px;
      color: #9CB8D8;
      line-height: 1.7;
      margin-bottom: 36px;
      max-width: 560px;
      margin-left: auto;
      margin-right: auto;
    }
    .btn-download {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      background: #1A4A8A;
      color: white;
      font-size: 15px;
      font-weight: 600;
      padding: 14px 32px;
      border-radius: 8px;
      text-decoration: none;
      border: 2px solid transparent;
      transition: all 0.2s;
      box-shadow: 0 4px 20px rgba(26,74,138,0.4);
    }
    .btn-download:hover {
      background: #2A5FA8;
      border-color: #7FB3E8;
      transform: translateY(-1px);
      box-shadow: 0 6px 24px rgba(26,74,138,0.5);
    }
    .btn-download svg { flex-shrink: 0; }
    .download-note {
      margin-top: 14px;
      font-size: 12px;
      color: #6B8BA8;
    }

    /* STATS */
    .stats {
      background: #1A3A5C;
      border-top: 1px solid rgba(255,255,255,0.07);
      padding: 24px 40px;
      display: flex;
      justify-content: center;
      gap: 0;
    }
    .stat {
      text-align: center;
      padding: 0 40px;
      border-right: 1px solid rgba(255,255,255,0.1);
    }
    .stat:last-child { border-right: none; }
    .stat-num { font-size: 22px; font-weight: 700; color: #7FB3E8; }
    .stat-lbl { font-size: 11px; color: #6B8BA8; margin-top: 2px; }

    /* FEATURES */
    .features {
      max-width: 960px;
      margin: 60px auto;
      padding: 0 40px;
    }
    .features-title {
      text-align: center;
      font-size: 22px;
      font-weight: 700;
      color: #1C2B3A;
      margin-bottom: 8px;
    }
    .features-sub {
      text-align: center;
      color: #6B7280;
      font-size: 14px;
      margin-bottom: 40px;
    }
    .features-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
    }
    .feature-card {
      background: white;
      border: 1px solid #DDE1E7;
      border-radius: 10px;
      padding: 24px;
      transition: box-shadow 0.2s, border-color 0.2s;
    }
    .feature-card:hover {
      border-color: #1A4A8A;
      box-shadow: 0 4px 16px rgba(26,74,138,0.1);
    }
    .feature-icon {
      width: 40px; height: 40px;
      background: #E8EFF7;
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-size: 20px;
      margin-bottom: 14px;
    }
    .feature-card h3 { font-size: 14px; font-weight: 600; color: #1C2B3A; margin-bottom: 8px; }
    .feature-card p { font-size: 13px; color: #6B7280; line-height: 1.6; }

    /* STEPS */
    .steps-section {
      background: white;
      border-top: 1px solid #DDE1E7;
      border-bottom: 1px solid #DDE1E7;
      padding: 56px 40px;
    }
    .steps-inner { max-width: 960px; margin: 0 auto; }
    .steps-title {
      text-align: center;
      font-size: 22px;
      font-weight: 700;
      color: #1C2B3A;
      margin-bottom: 8px;
    }
    .steps-sub {
      text-align: center;
      color: #6B7280;
      font-size: 14px;
      margin-bottom: 40px;
    }
    .steps-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    .step-card {
      display: flex;
      gap: 14px;
      align-items: flex-start;
      background: #F5F6F8;
      border-radius: 10px;
      padding: 18px;
      border-left: 3px solid #1A4A8A;
    }
    .step-num {
      font-size: 22px;
      font-weight: 700;
      color: #1A4A8A;
      line-height: 1;
      min-width: 28px;
    }
    .step-content h4 { font-size: 13px; font-weight: 600; color: #1C2B3A; margin-bottom: 4px; }
    .step-content p { font-size: 12px; color: #6B7280; line-height: 1.5; }

    /* CTA */
    .cta {
      background: #1C2B3A;
      padding: 56px 40px;
      text-align: center;
      border-top: 3px solid #C8A84B;
    }
    .cta h2 { font-size: 26px; font-weight: 700; color: white; margin-bottom: 12px; }
    .cta p { color: #9CB8D8; font-size: 15px; margin-bottom: 28px; }

    /* FOOTER */
    footer {
      background: #111B27;
      color: #4B5C70;
      text-align: center;
      padding: 20px 40px;
      font-size: 12px;
    }

    @media (max-width: 700px) {
      .hero h1 { font-size: 28px; }
      .features-grid, .steps-grid { grid-template-columns: 1fr; }
      .stats { flex-wrap: wrap; }
      .stat { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.1); padding: 12px 20px; }
      .stat:last-child { border-bottom: none; }
    }
  </style>
</head>
<body>

  <nav>
    <div class="nav-brand">
      <div class="nav-logo">OGSA</div>
      <span class="nav-name">Auditorías Comerciales</span>
    </div>
    <span class="nav-badge">EN PRODUCCIÓN</span>
  </nav>

  <section class="hero">
    <div class="hero-inner">
      <p class="hero-eyebrow">OGSA Auditores · Syngenta Argentina</p>
      <h1>Sistema de<br/><span>Auditorías Comerciales</span></h1>
      <p>
        Plataforma integral para auditar distribuidores de Syngenta Argentina.
        Automatizá cruces de datos, clasificación con IA y generación de informes
        — todo desde una aplicación de escritorio.
      </p>
      <a href="/download" class="btn-download">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        Descargar instalador (.exe)
      </a>
      <p class="download-note">Windows 10/11 · ~80 MB · Requiere conexión a internet</p>
    </div>
  </section>

  <div class="stats">
    <div class="stat"><div class="stat-num">6</div><div class="stat-lbl">Pasos de auditoría</div></div>
    <div class="stat"><div class="stat-num">100%</div><div class="stat-lbl">Proceso automatizado</div></div>
    <div class="stat"><div class="stat-num">IA</div><div class="stat-lbl">Claude Opus 4.5</div></div>
    <div class="stat"><div class="stat-num">ARS/USD</div><div class="stat-lbl">Multi-moneda</div></div>
    <div class="stat"><div class="stat-num">Cloud</div><div class="stat-lbl">Datos centralizados</div></div>
  </div>

  <section class="features">
    <h2 class="features-title">Todo lo que necesitás para auditar</h2>
    <p class="features-sub">Sin Excel manual. Sin errores de tipeo. Sin horas perdidas.</p>
    <div class="features-grid">
      <div class="feature-card">
        <div class="feature-icon">🔐</div>
        <h3>Multi-usuario con roles</h3>
        <p>Administradores y auditores. Cada usuario ve solo lo que necesita. Sesiones seguras con JWT.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">💱</div>
        <h3>Conversión ARS / USD</h3>
        <p>Tipo de cambio del período cargado por archivo. Todos los cálculos en USD de forma automática.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">🤖</div>
        <h3>Clasificación con IA</h3>
        <p>Claude Opus 4.5 clasifica productos como Agroquímico y Syngenta, y genera justificaciones de diferencias CRM.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📁</div>
        <h3>Expedientes por distribuidor</h3>
        <p>Cada DS y año tiene su propio expediente con progreso persistente y archivos asociados.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">📊</div>
        <h3>Exportación Excel formateada</h3>
        <p>Informes con 3 anexos (Compras, Agroquímicos, CRM) con estilos OGSA listos para entregar.</p>
      </div>
      <div class="feature-card">
        <div class="feature-icon">☁️</div>
        <h3>Datos en la nube</h3>
        <p>Base de datos centralizada en Railway. Todos los auditores ven los mismos datos en tiempo real.</p>
      </div>
    </div>
  </section>

  <section class="steps-section">
    <div class="steps-inner">
      <h2 class="steps-title">6 pasos, un proceso claro</h2>
      <p class="steps-sub">Cada paso se habilita al completar el anterior. Sin salteos, sin errores de secuencia.</p>
      <div class="steps-grid">
        <div class="step-card">
          <div class="step-num">01</div>
          <div class="step-content">
            <h4>Cruce Gestión vs. ARCA</h4>
            <p>Concilia comprobante por comprobante entre el ERP y los emitidos en AFIP. En USD, negando NC.</p>
          </div>
        </div>
        <div class="step-card">
          <div class="step-num">02</div>
          <div class="step-content">
            <h4>Análisis de Ventas</h4>
            <p>Ranking clientes y productos. Muestreo de 70. IA clasifica agroquímicos y productos Syngenta.</p>
          </div>
        </div>
        <div class="step-card">
          <div class="step-num">03</div>
          <div class="step-content">
            <h4>Cruce CRM Syngenta</h4>
            <p>Compara ventas de gestión vs CRM. Claude genera justificaciones automáticas por diferencia.</p>
          </div>
        </div>
        <div class="step-card">
          <div class="step-num">04</div>
          <div class="step-content">
            <h4>Análisis de Compras</h4>
            <p>Comprobantes recibidos de ARCA convertidos a USD. Resumen mensual por proveedor.</p>
          </div>
        </div>
        <div class="step-card">
          <div class="step-num">05</div>
          <div class="step-content">
            <h4>Informe Ejecutivo</h4>
            <p>Excel con Anexo I (Compras top 90%), Anexo II (Agroquímicos) y Anexo III (CRM).</p>
          </div>
        </div>
        <div class="step-card">
          <div class="step-num">06</div>
          <div class="step-content">
            <h4>Informe + Glosario IA</h4>
            <p>Igual al Paso 5 con columna "Nombre Glosario" mapeada por IA al estándar institucional.</p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="cta">
    <h2>Instalá el sistema en minutos</h2>
    <p>Un clic para instalar. Actualizable sin reinstalar. Funciona en cualquier equipo Windows.</p>
    <a href="/download" class="btn-download">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
      Descargar OGSA Auditorías
    </a>
  </section>

  <footer>
    OGSA Auditores &copy; 2026 &nbsp;·&nbsp; oag.up.railway.app &nbsp;·&nbsp; Confidencial
  </footer>

</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def landing():
    return LANDING_HTML


@app.get("/download")
def download():
    return RedirectResponse(url=GITHUB_RELEASE_URL)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


# Crear usuario admin inicial si no existe
from .core.database import SessionLocal
from .core.auth import get_password_hash
from .models.user import User, UserRole


def create_initial_admin():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing:
            print(f"✓ Admin ya existe: {existing.email}")
        else:
            admin = User(
                email="admin@ogsa.com",
                nombre="Administrador OGSA",
                hashed_password=get_password_hash("ogsa2024"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print("✓ Usuario admin creado: admin@ogsa.com / ogsa2024")
    except Exception as e:
        print(f"✗ Error creando admin: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


create_initial_admin()
