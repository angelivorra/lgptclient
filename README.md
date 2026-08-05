# lgptclient — robot de percusión

Ver [CLAUDE.md](CLAUDE.md) para la arquitectura completa (flujo de eventos,
estructura de directorios, stack) y el flujo de despliegue por Ansible.

## Desplegar

```bash
ansible-playbook ansible/actualiza-todo.yaml -i ansible/inventario
```

O por nodo: `ansible/actualiza-sinte.yaml`, `ansible/actualiza-maletas.yaml`,
`ansible/actualiza-vocoder.yaml` (mismo `-i ansible/inventario`).

## Generar miniaturas / imágenes de cliente

```bash
venv/bin/python bin/genera.py <maleta|sombrilla>
```

Genera en `img_output/<host>/` las imágenes que el rol `cliente-actualiza`
sincroniza al robot correspondiente.
