#!/usr/bin/env python3
"""
Scheduler asíncrono para ejecutar tareas en timestamps precisos.

Características:
- Usa heap para mantener eventos ordenados por tiempo
- Precisión de milisegundos con time.monotonic()
- Método clear_queue() para limpiar eventos pendientes (STOP)
"""
import asyncio
import time
import heapq
import logging
from dataclasses import dataclass, field
from typing import Callable, Tuple, List

logger = logging.getLogger("cliente.scheduler")


@dataclass(order=True)
class ScheduledTask:
    """Tarea programada para ejecutar en un momento específico."""
    due_mono: float = field(compare=True)
    seq: int = field(compare=False)
    callback: Callable = field(compare=False)
    args: Tuple = field(compare=False, default_factory=tuple)
    kwargs: dict = field(compare=False, default_factory=dict)
    description: str = field(compare=False, default="")


class Scheduler:
    """Scheduler asíncrono para ejecutar callbacks en momentos precisos."""
    
    def __init__(self):
        self._heap: List[ScheduledTask] = []
        self._seq = 0
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
            wall_time_ms: Timestamp absoluto en milisegundos
            callback: Función a ejecutar
            args: Argumentos posicionales
            kwargs: Argumentos nombrados
            description: Descripción para logging
        """
        if kwargs is None:
            kwargs = {}
        
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
        
        self._new_task_event.set()
    
    def schedule_in(
        self,
        delay_ms: float,
        callback: Callable,
        args: Tuple = (),
        kwargs: dict = None,
        description: str = ""
    ):
        """Programa una tarea para ejecutar después de un delay relativo."""
        wall_time_ms = int(time.time() * 1000 + delay_ms)
        self.schedule_at_walltime(wall_time_ms, callback, args, kwargs, description)
    
    def clear_queue(self) -> int:
        """
        Limpia todas las tareas pendientes de la cola.
        
        Returns:
            Número de tareas eliminadas
        """
        count = len(self._heap)
        self._heap.clear()
        if count > 0:
            logger.info(f"🗑️  Cola limpiada: {count} tareas pendientes eliminadas")
        return count
    
    def get_pending_count(self) -> int:
        """Retorna el número de tareas pendientes."""
        return len(self._heap)
    
    async def start(self):
        """Inicia el scheduler."""
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
        self._new_task_event.set()
        
        if self._runner_task:
            await self._runner_task
        
        logger.info(f"⏹️  Scheduler detenido (tareas pendientes: {len(self._heap)})")
    
    async def _run(self):
        """Loop principal del scheduler."""
        logger.debug("Scheduler runner iniciado")
        
        while self._running:
            if not self._heap:
                logger.debug("Cola vacía, esperando tareas...")
                self._new_task_event.clear()
                await self._new_task_event.wait()
                continue
            
            next_task = self._heap[0]
            now_mono = time.monotonic()
            wait_s = next_task.due_mono - now_mono
            
            if wait_s > 0.050:
                await asyncio.sleep(0.020)
                continue
            elif wait_s > 0.005:
                await asyncio.sleep(wait_s * 0.5)
                continue
            elif wait_s > 0:
                await asyncio.sleep(wait_s)
            
            task = heapq.heappop(self._heap)
            now_mono = time.monotonic()
            lateness_ms = (now_mono - task.due_mono) * 1000
            
            if lateness_ms > 15:
                logger.warning(
                    f"⚠️  Tarea #{task.seq} ejecutada con {lateness_ms:.1f}ms de retraso"
                )
            
            asyncio.create_task(self._execute_task(task))
    
    async def _execute_task(self, task: ScheduledTask):
        """Ejecuta una tarea programada."""
        try:
            logger.debug(f"▶️  Ejecutando tarea #{task.seq}: {task.description}")
            
            if asyncio.iscoroutinefunction(task.callback):
                await task.callback(*task.args, **task.kwargs)
            else:
                task.callback(*task.args, **task.kwargs)
            
            logger.debug(f"✅ Tarea #{task.seq} completada")
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando tarea #{task.seq}: {e}")
