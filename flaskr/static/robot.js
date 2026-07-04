const {
  createTheme,
  ThemeProvider,
  CssBaseline,
  AppBar,
  Toolbar,
  Typography,
  Box,
  Card,
  CardContent,
  LinearProgress,
  IconButton,
  Stack,
  Chip,
  Alert,
  Skeleton,
  Button,
  CircularProgress
} = MaterialUI;
const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#5c6bc0'
    },
    secondary: {
      main: '#ab47bc'
    },
    warning: {
      main: '#ffa726'
    },
    info: {
      main: '#29b6f6'
    },
    background: {
      default: '#0a0e1a',
      paper: '#141929'
    }
  },
  shape: {
    borderRadius: 12
  },
  typography: {
    fontFamily: 'Roboto, sans-serif'
  }
});
const D = JSON.parse(document.getElementById('flask-data').textContent);
function UsageBar({
  label,
  value,
  detail,
  color
}) {
  const pct = Math.min(value || 0, 100);
  const barColor = pct > 90 ? '#ef5350' : pct > 70 ? '#ffa726' : '#29b6f6';
  return /*#__PURE__*/React.createElement(Box, null, /*#__PURE__*/React.createElement(Box, {
    sx: {
      display: 'flex',
      justifyContent: 'space-between',
      mb: 0.5
    }
  }, /*#__PURE__*/React.createElement(Typography, {
    variant: "caption",
    sx: {
      fontWeight: 600
    }
  }, label), /*#__PURE__*/React.createElement(Typography, {
    variant: "caption",
    color: "text.secondary",
    sx: {
      fontFamily: 'monospace'
    }
  }, pct.toFixed(1), "%", detail ? ` · ${detail}` : '')), /*#__PURE__*/React.createElement(LinearProgress, {
    variant: "determinate",
    value: pct,
    sx: {
      height: 8,
      borderRadius: 4,
      '& .MuiLinearProgress-bar': {
        bgcolor: barColor
      }
    }
  }));
}
function App() {
  const [sysData, setSysData] = React.useState(null);
  const [status, setStatus] = React.useState(null);
  const [svcData, setSvcData] = React.useState(null);
  const [healthy, setHealthy] = React.useState(null);
  const [restarting, setRestarting] = React.useState(false);
  React.useEffect(() => {
    const fetchAll = () => {
      fetch('/robot_data').then(r => r.json()).then(setSysData).catch(() => {});
      fetch('/api/status').then(r => r.json()).then(setStatus).catch(() => {});
      fetch('/api/client-errors').then(r => r.json()).then(setSvcData).catch(() => {});
    };
    fetchAll();
    const id = setInterval(fetchAll, 5000);
    return () => clearInterval(id);
  }, []);
  React.useEffect(() => {
    const check = () => {
      fetch('/api/health', {
        signal: AbortSignal.timeout(3000)
      }).then(r => r.ok ? r.json() : Promise.reject()).then(() => setHealthy(true)).catch(() => setHealthy(false));
    };
    check();
    const id = setInterval(check, 5000);
    return () => clearInterval(id);
  }, []);
  const nombre = status?.nombre || D.name;
  const isDebug = !!status?.debug;
  const svcOk = svcData?.is_active ?? null;
  const errors = svcData?.errors || '';
  return /*#__PURE__*/React.createElement(ThemeProvider, {
    theme: theme
  }, /*#__PURE__*/React.createElement(CssBaseline, null), /*#__PURE__*/React.createElement(AppBar, {
    position: "sticky",
    elevation: 0,
    sx: {
      bgcolor: 'background.paper',
      borderBottom: '1px solid rgba(255,255,255,0.07)'
    }
  }, /*#__PURE__*/React.createElement(Toolbar, {
    variant: "dense"
  }, /*#__PURE__*/React.createElement(IconButton, {
    edge: "start",
    color: "inherit",
    onClick: () => history.back(),
    sx: {
      mr: 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "material-icons"
  }, "arrow_back")), /*#__PURE__*/React.createElement(Typography, {
    variant: "h6",
    sx: {
      flexGrow: 1,
      fontWeight: 700,
      textTransform: 'capitalize'
    }
  }, nombre), /*#__PURE__*/React.createElement(Chip, {
    size: "small",
    label: healthy === null ? '…' : healthy ? 'Online' : 'Sin respuesta',
    color: healthy === null ? 'default' : healthy ? 'success' : 'error',
    sx: {
      fontWeight: 600
    }
  }))), /*#__PURE__*/React.createElement(Box, {
    sx: {
      p: 2,
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, /*#__PURE__*/React.createElement(Card, null, /*#__PURE__*/React.createElement(CardContent, {
    sx: {
      display: 'flex',
      alignItems: 'center',
      gap: 2
    }
  }, /*#__PURE__*/React.createElement(Box, {
    sx: {
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("img", {
    src: `/static/${D.name.toLowerCase()}.png`,
    alt: nombre,
    style: {
      width: 80,
      height: 80,
      objectFit: 'contain'
    },
    onError: e => {
      e.target.style.display = 'none';
    }
  })), /*#__PURE__*/React.createElement(Box, {
    sx: {
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      gap: 0.75
    }
  }, /*#__PURE__*/React.createElement(Typography, {
    variant: "subtitle1",
    sx: {
      fontWeight: 700,
      textTransform: 'capitalize'
    }
  }, nombre), /*#__PURE__*/React.createElement(Stack, {
    direction: "row",
    spacing: 0.75,
    flexWrap: "wrap",
    useFlexGap: true
  }, status ? /*#__PURE__*/React.createElement(Chip, {
    size: "small",
    label: isDebug ? 'Debug' : 'Producción',
    color: isDebug ? 'warning' : 'success',
    icon: /*#__PURE__*/React.createElement("span", {
      className: "material-icons",
      style: {
        fontSize: 13
      }
    }, isDebug ? 'bug_report' : 'play_circle')
  }) : /*#__PURE__*/React.createElement(Skeleton, {
    variant: "rounded",
    width: 80,
    height: 22
  }), svcData ? /*#__PURE__*/React.createElement(Chip, {
    size: "small",
    label: svcOk ? 'Conectado' : 'Desconectado',
    color: svcOk ? 'success' : 'error',
    icon: /*#__PURE__*/React.createElement("span", {
      className: "material-icons",
      style: {
        fontSize: 13
      }
    }, svcOk ? 'lan' : 'lan')
  }) : /*#__PURE__*/React.createElement(Skeleton, {
    variant: "rounded",
    width: 90,
    height: 22
  }), status?.ruido !== undefined && /*#__PURE__*/React.createElement(Chip, {
    size: "small",
    label: "Motores",
    color: status.ruido ? 'primary' : 'default',
    variant: status.ruido ? 'filled' : 'outlined'
  }), status?.pantalla !== undefined && /*#__PURE__*/React.createElement(Chip, {
    size: "small",
    label: "Pantalla",
    color: status.pantalla ? 'primary' : 'default',
    variant: status.pantalla ? 'filled' : 'outlined'
  }))))), /*#__PURE__*/React.createElement(Card, null, /*#__PURE__*/React.createElement(CardContent, null, /*#__PURE__*/React.createElement(Box, {
    sx: {
      display: 'flex',
      alignItems: 'center',
      gap: 1,
      mb: 1.5
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "material-icons",
    style: {
      fontSize: 18,
      color: '#29b6f6'
    }
  }, "storage"), /*#__PURE__*/React.createElement(Typography, {
    variant: "subtitle1",
    sx: {
      fontWeight: 600
    }
  }, "Disco")), sysData ? /*#__PURE__*/React.createElement(UsageBar, {
    value: sysData.disk_usage_percent,
    detail: sysData.disk_usage_string
  }) : /*#__PURE__*/React.createElement(Skeleton, {
    variant: "rounded",
    height: 28
  }))), /*#__PURE__*/React.createElement(Card, null, /*#__PURE__*/React.createElement(CardContent, null, /*#__PURE__*/React.createElement(Box, {
    sx: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      mb: 1
    }
  }, /*#__PURE__*/React.createElement(Box, {
    sx: {
      display: 'flex',
      alignItems: 'center',
      gap: 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "material-icons",
    style: {
      fontSize: 18,
      color: svcOk ? '#66bb6a' : '#ef5350'
    }
  }, svcOk ? 'check_circle' : 'error'), /*#__PURE__*/React.createElement(Typography, {
    variant: "subtitle1",
    sx: {
      fontWeight: 600
    }
  }, "Servicio cliente")), /*#__PURE__*/React.createElement(Stack, {
    direction: "row",
    spacing: 1,
    alignItems: "center"
  }, /*#__PURE__*/React.createElement(Chip, {
    size: "small",
    label: svcOk === null ? '…' : svcOk ? 'Activo' : 'Inactivo',
    color: svcOk === null ? 'default' : svcOk ? 'success' : 'error'
  }), /*#__PURE__*/React.createElement(Button, {
    size: "small",
    variant: "outlined",
    color: "warning",
    disabled: restarting,
    onClick: () => {
      setRestarting(true);
      fetch('/restart-cliente', {
        method: 'POST'
      }).finally(() => setTimeout(() => setRestarting(false), 3000));
    },
    startIcon: restarting ? /*#__PURE__*/React.createElement(CircularProgress, {
      size: 12,
      color: "inherit"
    }) : /*#__PURE__*/React.createElement("span", {
      className: "material-icons",
      style: {
        fontSize: 14
      }
    }, "restart_alt"),
    sx: {
      minWidth: 0,
      px: 1
    }
  }, restarting ? '' : 'Reiniciar'))), svcData === null ? /*#__PURE__*/React.createElement(Skeleton, {
    variant: "rounded",
    height: 60
  }) : errors ? /*#__PURE__*/React.createElement(Box, {
    component: "pre",
    sx: {
      fontSize: '0.65rem',
      whiteSpace: 'pre-wrap',
      overflowX: 'auto',
      maxHeight: 200,
      bgcolor: 'rgba(239,83,80,0.08)',
      border: '1px solid rgba(239,83,80,0.2)',
      color: '#ef9a9a',
      p: 1,
      borderRadius: 1,
      m: 0
    }
  }, errors) : /*#__PURE__*/React.createElement(Typography, {
    variant: "body2",
    color: "text.secondary"
  }, "Sin errores recientes")))));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));
