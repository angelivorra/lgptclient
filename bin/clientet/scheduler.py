#!/usr/bin/env python3
"""
Scheduler asíncrono genérico para ejecutar tareas en timestamps precisos.

Usa un heap para mantener eventos ordenados por tiempo de ejecución.
Soporta ejecución con precisión de milisegundos usando time.monotonic().
"""
import asyncio
import time
import heapq
import logging
from dataclasses import dataclass, field
from typing import Callable, Any, Tuple, List
from collections.abc import Coroutine

logger = logging.getLogger("clientet.scheduler")


@dataclass(order=True)
class ScheduledTask:
    """Tarea programada para ejecutar en un momento específico."""
    
    due_mono: float = field(compare=True)  # Tiempo monotónico de ejecución
    seq: int = field(compare=False)        # Secuencia para desempate
    callback: Callable = field(compare=False)  # Función a ejecutar
    args: Tuple = field(compare=False, default_factory=tuple)  # Argumentos
    kwargs: dict = field(compare=False, default_factory=dict)  # Kwargs
    description: str = field(compare=False, default="")  # Descripción para logging


class Scheduler:
    """
    Scheduler asíncrono para ejecutar callbacks en momentos precisos.
    
    Características:
    - Usa time.monotonic() para evitar problemas con cambios de reloj del sistema
    - Mantiene cola ordenada con heap
    - Ejecuta tareas con precisión de milisegundos
    - Soporta callbacks síncronos y asíncronos
    """
    
    def __init__(self):
        self._heap: List[ScheduledTask] = []
        self._seq = 0  # Contador para desempate de tareas con mismo timestamp
        self._new_task_event = asyncio.Event()
        self._running = False
        self._runner_task = None
    
    def schedule_at_walltime(
        self,
        wall_time_ms: int,
        callback: Callable,
        args: Tuple = (),
        kwargs: dict = None,
        description: str = ""
    ):
        """
        Programa una tarea para ejecutar en un tiempo específico (wall clock).
        
        Args:
            wall_time_ms: Timestamp absoluto en milisegundos (time.time() * 1000)
            callback: Función a ejecutar (puede ser async o sync)
            args: Argumentos posicionales para el callback
            kwargs: Argumentos nombrados para el callback
            description: Descripción para logging
        """
        if kwargs is None:
            kwargs = {}
        
        # Convertir wall time a monotonic time
        now_wall_ms = time.time() * 1000
        now_mono = time.monotonic()
        delta_ms = wall_time_ms - now_wall_ms
        due_mono = now_mono + (delta_ms / 1000.0)
        
        self._seq += 1
        task = ScheduledTask(
            due_mono=due_mono,
            seq=self._seq,
            callback=callback,
            args=args,
            kwargs=kwargs,
            description=description
        )
        
        heapq.heappush(self._heap, task)
        
        wait_ms = max(delta_ms, 0)
        logger.debug(
            f"📅 Programada tarea #{self._seq}: {description} "
            f"(en {wait_ms:.1f}ms) | Cola: {len(self._heap)} tareas"
        )
        
        # Notificar al runner que hay una nueva tarea
        self._new_task_event.set()
    
    def schedule_in(
        self,
        delay_ms: float,
        callback: Callable,
        args: Tuple = (),
        kwargs: dict = None,
        description: str = ""
    ):
        """
        Programa una tarea para ejecutar después de un delay relativo.
        
        Args:
            delay_ms: Delay en milisegundos desde ahora
            callback: Función a ejecutar
            args: Argumentos posicionales
            kwargs: Argumentos nombrados
            description: Descripción para logging
        """
        wall_time_ms = int(time.time() * 1000 + delay_ms)
        self.schedule_at_walltime(wall_time_ms, callback, args, kwargs, description)
    
    async def start(self):
        """Inicia el scheduler (crea tarea de background)."""
        if self._running:
            logger.warning("Scheduler ya está corriendo")
            return
        
        self._running = True
        self._runner_task = asyncio.create_task(self._run())
        logger.info("✅ Scheduler iniciado")
    
    async def stop(self):
        """Detiene el scheduler."""
        if not self._running:
            return
        
        self._running = False
        self._new_task_event.set()  # Despertar al runner
        
        if self._runner_task:
            await self._runner_task
        
        logger.info(f"⏹️  Scheduler detenido (tareas pendientes: {len(self._heap)})")
    
    async def _run(self):
        """Loop principal del scheduler."""
        logger.debug("Scheduler runner iniciado")
        
        while self._running:
            if not self._heap:
                # No hay tareas, esperar a que se agregue una
                logger.debug("Cola vacía, esperando tareas...")
                self._new_task_event.clear()
                await self._new_task_event.wait()
                continue
            
            # Obtener la siguiente tarea (sin sacarla aún del heap)
            next_task = self._heap[0]
            now_mono = time.monotonic()
            wait_s = next_task.due_mono - now_mono
            
            if wait_s > 0.010:  # Más de 10ms
                # Esperar de forma eficiente
                sleep_time = min(wait_s * 0.5, 0.050)  # Máximo 50ms
                await asyncio.sleep(sleep_time)
                continue
            elif wait_s > 0:  # Entre 0 y 10ms
                # Espera fina
                await asyncio.sleep(wait_s)
            
            # Es hora de ejecutar
            task = heapq.heappop(self._heap)
            
            # Calcular latencia
            now_mono = time.monotonic()
            lateness_ms = (now_mono - task.due_mono) * 1000
            
            if lateness_ms > 5:  # Umbral de advertencia
                logger.warning(
                    f"⚠️  Tarea #{task.seq} ejecutada con {lateness_ms:.1f}ms de retraso"
                )
            
            # Ejecutar la tarea
            await self._execute_task(task)
    
    async def _execute_task(self, task: ScheduledTask):
        """Ejecuta una tarea programada."""
        try:
            logger.debug(f"▶️  Ejecutando tarea #{task.seq}: {task.description}")
            
            # Verificar si el callback es una coroutine
            if asyncio.iscoroutinefunction(task.callback):
                await task.callback(*task.args, **task.kwargs)
            else:
                # Ejecutar callback síncrono
                task.callback(*task.args, **task.kwargs)
            
            logger.debug(f"✅ Tarea #{task.seq} completada")
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando tarea #{task.seq}: {e}", exc_info=True)
    
    def get_pending_count(self) -> int:
        """Retorna el número de tareas pendientes."""
        return len(self._heap)
    
    def is_running(self) -> bool:
        """Retorna True si el scheduler está corriendo."""
        return self._running


if __name__ == '__main__':
    # Test del scheduler
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    async def test_callback(name: str, value: int):
        logger.info(f"🎯 Callback ejecutado: {name} = {value}")
    
    async def test_scheduler():
        scheduler = Scheduler()
        await scheduler.start()
        
        logger.info("\n" + "="*60)
        logger.info("Test del Scheduler")
        logger.info("="*60)
        
        # Programar varias tareas
        scheduler.schedule_in(100, test_callback, ("Tarea 1", 100), description="Test 100ms")
        scheduler.schedule_in(500, test_callback, ("Tarea 2", 500), description="Test 500ms")
        scheduler.schedule_in(200, test_callback, ("Tarea 3", 200), description="Test 200ms")
        scheduler.schedule_in(1000, test_callback, ("Tarea 4", 1000), description="Test 1000ms")
        
        # Esperar a que se ejecuten todas
        await asyncio.sleep(1.5)
        
        await scheduler.stop()
        logger.info("Test completado")
    
    asyncio.run(test_scheduler())
