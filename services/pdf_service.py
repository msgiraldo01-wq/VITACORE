"""
Servicio de generación de PDFs vía Playwright (Chromium headless).
Reutilizable para citas, evoluciones, fórmulas, etc.
"""

import asyncio
import io
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright


class PDFService:
    """Genera PDFs profesionales desde HTML usando Chromium."""
    
    # Configuración por defecto (carta)
    DEFAULT_PAPER = {
        "format": "Letter",
        "margin": {
            "top": "1.5cm",
            "right": "1.5cm", 
            "bottom": "1.5cm",
            "left": "1.5cm"
        },
        "print_background": True,
        "prefer_css_page_size": False,
    }
    
    @classmethod
    async def html_to_pdf(
        cls,
        html_content: str,
        paper_config: Optional[dict] = None,
        wait_for_network: bool = True
    ) -> bytes:
        """
        Convierte HTML string a bytes PDF.
        
        Args:
            html_content: HTML completo como string
            paper_config: Override de DEFAULT_PAPER
            wait_for_network: Esperar a que carguen recursos externos
        
        Returns:
            bytes del PDF generado
        """
        config = {**cls.DEFAULT_PAPER, **(paper_config or {})}
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Cargar HTML
            await page.set_content(
                html_content, 
                wait_until="networkidle" if wait_for_network else "load"
            )
            
            # Generar PDF
            pdf_bytes = await page.pdf(**config)
            
            await browser.close()
            return pdf_bytes
    
    @classmethod
    def sync_html_to_pdf(cls, *args, **kwargs) -> bytes:
        """Wrapper síncrono para usar desde Flask sync."""
        return asyncio.run(cls.html_to_pdf(*args, **kwargs))


class AssetHelper:
    """Helper para embeber assets (imágenes, fuentes) como base64."""
    
    @staticmethod
    def img_to_base64(path: str | Path) -> Optional[str]:
        """Convierte imagen a data URI base64."""
        try:
            path = Path(path)
            if not path.exists():
                return None
                
            import base64
            ext = path.suffix.lower().replace(".", "")
            mime = {
                "png": "image/png",
                "jpg": "image/jpeg", 
                "jpeg": "image/jpeg",
                "svg": "image/svg+xml"
            }.get(ext, "image/png")
            
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                return f"data:{mime};base64,{b64}"
        except Exception:
            return None