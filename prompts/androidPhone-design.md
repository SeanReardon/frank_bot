# androidPhone Feature Design

## Overview

The `androidPhone*` family of actions enables Frank Bot to control mobile apps on a dedicated Android device via ADB (**USB preferred**, wireless debugging optional). Unlike simple API calls, these actions require an LLM-in-the-loop to handle variable phone UX.

## Device Configuration

| Setting | Value |
|---------|-------|
| USB Serial (preferred) | 48151FDKD001UD |
| Wi‑Fi Debug Host (optional) | _unset_ (set explicitly if used) |
| Wi‑Fi Debug Port (optional) | 5555 |
| Device | Google Pixel 9 Pro Fold |
| OS | Android 16 |
| Root | Magisk |
| Wake Mode | Screen on while charging |

## Architecture

```
User Request (ChatGPT / Telegram / SMS)
    "Set the thermostat to 68-72 degrees"
                    ↓
          REST Endpoint
    /actions/androidPhone/thermostat/setRange
                    ↓
        Load Prompt Template
      (prompts/androidPhone/thermostat-setRange.md)
                    ↓
        AndroidPhoneRunner Loop
        ┌─────────────────────────────┐
        │  1. Wake phone if needed    │
        │  2. Launch Google Home      │
        │  3. Get screen XML + image  │
        │  4. LLM interprets screen   │
        │  5. LLM decides action      │
        │  6. Execute (tap/type/etc)  │
        │  7. Get new screen state    │
        │  8. Loop until complete     │
        └─────────────────────────────┘
                    ↓
        Return Status to User
    "Thermostat set to 68-72°F. Currently 70°F."
```

## Naming Convention

All Android phone actions use the prefix `androidPhone`:

```
# Diagnostics & Core
/actions/androidPhone/status                    # Device connection status
/actions/androidPhone/apps                      # List installed apps
/actions/androidPhone/getScreen                 # Get current screen (image + XML)
/actions/androidPhone/health                    # Full health check

# Thermostat (MVP)
/actions/androidPhone/thermostat/setRange       # Set temp range (e.g., 68-72°F)
/actions/androidPhone/thermostat/getStatus      # Get current temp and settings

# Uber
/actions/androidPhone/uber/requestRide          # Request an Uber
/actions/androidPhone/uber/getRideStatus        # Check ride status
/actions/androidPhone/uber/cancelRide           # Cancel current ride

# Uber Eats
/actions/androidPhone/ubereats/orderFood        # Order from Uber Eats
/actions/androidPhone/ubereats/getOrderStatus   # Check order status

# OpenTable
/actions/androidPhone/opentable/reserve         # Make a reservation
/actions/androidPhone/opentable/getReservations # List reservations
/actions/androidPhone/opentable/cancel          # Cancel reservation

# American Airlines
/actions/androidPhone/aa/getFlightStatus        # Check flight status
/actions/androidPhone/aa/getBoardingPass        # Get boarding pass info

# Zillow
/actions/androidPhone/zillow/getEstimate        # Property value estimate
/actions/androidPhone/zillow/search             # Search properties

# Maintenance
/actions/androidPhone/maintenance/updateApps    # Update outdated apps
/actions/androidPhone/maintenance/checkSecurity # Check security patch status
/actions/androidPhone/maintenance/clearCache    # Clear app caches
/actions/androidPhone/maintenance/reboot        # Reboot device
```

---

## Core Diagnostic Actions

### `androidPhoneGetScreen` (MVP Diagnostic)

Returns the current screen state as both:
1. **Screenshot image** (PNG) - for visual inspection
2. **Accessibility XML** - for programmatic understanding

This is the fundamental building block for debugging and manual control.

```python
async def androidPhone_getScreen(arguments: dict) -> dict:
    """
    Get the current screen state - image + accessibility tree.
    
    Returns:
        - screenshot_base64: PNG image encoded as base64
        - screenshot_path: Local path to saved image
        - screen_xml: Raw accessibility XML
        - elements: Parsed clickable/text elements
        - current_app: Package name of foreground app
    """
```

**Use cases:**
- Debug what the phone is showing
- Manual intervention when automation fails
- Training data for prompt improvement
- Visual confirmation of task completion

### `androidPhoneHealth`

Comprehensive health check:
- Device connection status
- Battery level
- WiFi signal strength
- Storage available
- Running apps
- Pending app updates
- Security patch level
- ADB daemon status

---

## Prompt Templates

Each action has a pre-packaged prompt template stored in `prompts/androidPhone/`:

```
prompts/androidPhone/
├── _base.md                        # Common phone control instructions
├── _screen-reading.md              # How to interpret accessibility XML
├── _error-recovery.md              # Common error patterns and recovery
│
├── thermostat-setRange.md          # MVP: Set thermostat range
├── thermostat-getStatus.md         # Get thermostat status
│
├── uber-requestRide.md             # Request Uber ride
├── uber-getRideStatus.md           # Check ride status
├── uber-cancelRide.md              # Cancel ride
│
├── ubereats-orderFood.md           # Order food
├── ubereats-getOrderStatus.md      # Check order
│
├── opentable-reserve.md            # Make reservation
├── opentable-getReservations.md    # List reservations
│
├── aa-getFlightStatus.md           # Flight status
├── aa-getBoardingPass.md           # Boarding pass
│
├── zillow-getEstimate.md           # Property estimate
│
├── maintenance-updateApps.md       # Update apps
├── maintenance-checkSecurity.md    # Security check
└── maintenance-fullHealth.md       # Complete health audit
```

### Prompt Template Structure

```markdown
# androidPhone: Thermostat Set Range

## Goal
Set the home thermostat to maintain temperature within a specified range.

## Parameters
- `low_temp` (required): Minimum temperature in Fahrenheit
- `high_temp` (required): Maximum temperature in Fahrenheit
- `mode` (optional): "heat", "cool", "auto" (default: "auto")

## App Information
- Package: com.google.android.apps.chromecast.app (Google Home)
- Entry point: Home tab → Thermostat device
- Expected state: Logged in, thermostat already added

## Workflow Steps
1. Launch Google Home app
2. Navigate to home tab (if not already there)
3. Find and tap the thermostat device
4. Locate temperature controls
5. Set heating minimum to $low_temp
6. Set cooling maximum to $high_temp
7. Verify settings applied
8. Return to home screen

## Success Criteria
- Temperature range confirmed as $low_temp - $high_temp
- Return: current_temp, set_range, mode

## Error Handling
- If thermostat not found: List available devices, report error
- If app not logged in: Pause and notify user
- If device offline: Report "thermostat offline"
- If temp out of range: Report valid range limits

## Known UI Patterns
- Thermostat card shows current temp prominently
- Tap card to open detailed controls
- Range mode shows two sliders (heat/cool)
- "Done" or back button to save
```

---

## Automated Maintenance Jorbs

### Monthly Phone Health Check

A scheduled jorb that runs monthly to ensure the phone stays healthy:

```yaml
name: "androidPhone Monthly Maintenance"
schedule: "0 3 1 * *"  # 3 AM on the 1st of each month
personality: "expeditor"
tasks:
  - Check device connection and health
  - Review and install app updates
  - Check Android security patch status
  - Clear app caches if storage low
  - Verify all automation apps still working
  - Report any issues to Sean via Telegram
```

**Implementation:**
- Create as a recurring jorb in the jorb system
- Uses maintenance prompt templates
- Logs results to progress_log
- Sends Telegram notification with summary

### Weekly Quick Health Check

```yaml
name: "androidPhone Weekly Health"
schedule: "0 4 * * 0"  # 4 AM every Sunday
tasks:
  - Verify device connection
  - Check battery (should be 100% if charging)
  - Check WiFi connection
  - Test one app launch (Google Home)
  - Report only if issues found
```

---

## Implementation Components

### 1. `services/android_phone_runner.py`

The core LLM loop orchestrator:

```python
class AndroidPhoneRunner:
    """
    Orchestrates LLM-driven phone automation tasks.
    
    Features:
    - Load and parameterize prompt templates
    - Perception-action loop with configurable max steps
    - Screenshot + XML capture at each step
    - Token tracking and cost estimation
    - Error recovery and retry logic
    - Progress logging
    """
    
    async def execute_task(
        self,
        prompt_template: str,
        params: dict[str, Any],
        max_steps: int = 30,
        timeout_seconds: int = 180,
    ) -> TaskResult:
        """Execute a phone automation task."""
        
    async def get_screen_state(self) -> ScreenState:
        """Capture current screen (image + XML + parsed elements)."""
        
    async def execute_action(self, action: PhoneAction) -> ActionResult:
        """Execute a single phone action (tap, type, swipe, etc.)."""
```

### 2. `actions/android_phone.py`

High-level action handlers:

```python
# Diagnostics
async def androidPhone_status(arguments) -> dict
async def androidPhone_apps(arguments) -> dict
async def androidPhone_getScreen(arguments) -> dict
async def androidPhone_health(arguments) -> dict

# Thermostat (MVP)
async def androidPhone_thermostat_setRange(arguments) -> dict
async def androidPhone_thermostat_getStatus(arguments) -> dict

# Uber
async def androidPhone_uber_requestRide(arguments) -> dict
async def androidPhone_uber_getRideStatus(arguments) -> dict

# ... etc for each action
```

### 3. `services/android_maintenance.py`

Maintenance job handling:

```python
class AndroidMaintenanceService:
    """Handles scheduled phone maintenance tasks."""
    
    async def run_monthly_maintenance(self) -> MaintenanceReport
    async def run_weekly_health_check(self) -> HealthReport
    async def update_apps(self) -> list[AppUpdateResult]
    async def check_security_patches(self) -> SecurityStatus
    async def clear_caches(self) -> CacheCleanupResult
```

### 4. Scheduled Jobs Integration

Add to `services/background_loop.py`:

```python
# Monthly phone maintenance (1st of month at 3 AM)
async def android_monthly_maintenance():
    service = AndroidMaintenanceService()
    report = await service.run_monthly_maintenance()
    if report.issues:
        await notify_sean(f"Phone maintenance issues: {report.summary}")

# Weekly health check (Sunday at 4 AM)  
async def android_weekly_health():
    service = AndroidMaintenanceService()
    report = await service.run_weekly_health_check()
    if not report.healthy:
        await notify_sean(f"Phone health issue: {report.summary}")
```

---

## API Endpoints (Full List)

### Diagnostic Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /actions/androidPhone/status` | Device connection status |
| `GET /actions/androidPhone/apps` | List installed apps |
| `GET /actions/androidPhone/getScreen` | **Screenshot + XML (key diagnostic)** |
| `GET /actions/androidPhone/health` | Full health check |

### Thermostat Endpoints (MVP)

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /actions/androidPhone/thermostat/setRange` | `low_temp`, `high_temp`, `mode` | Set temperature range |
| `GET /actions/androidPhone/thermostat/getStatus` | - | Get current status |

### Uber Endpoints

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /actions/androidPhone/uber/requestRide` | `from_address`, `to_address`, `ride_type` | Request ride |
| `GET /actions/androidPhone/uber/getRideStatus` | - | Check current ride |
| `GET /actions/androidPhone/uber/cancelRide` | - | Cancel ride |

### Uber Eats Endpoints

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /actions/androidPhone/ubereats/orderFood` | `restaurant`, `items` | Order food |
| `GET /actions/androidPhone/ubereats/getOrderStatus` | `order_id` | Check order |

### OpenTable Endpoints

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /actions/androidPhone/opentable/reserve` | `restaurant`, `date`, `time`, `party_size` | Make reservation |
| `GET /actions/androidPhone/opentable/getReservations` | - | List reservations |
| `GET /actions/androidPhone/opentable/cancel` | `reservation_id` | Cancel |

### American Airlines Endpoints

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /actions/androidPhone/aa/getFlightStatus` | `flight_number`, `date` | Flight status |
| `GET /actions/androidPhone/aa/getBoardingPass` | `confirmation_code` | Boarding pass |

### Zillow Endpoints

| Endpoint | Params | Description |
|----------|--------|-------------|
| `GET /actions/androidPhone/zillow/getEstimate` | `address` | Property estimate |
| `GET /actions/androidPhone/zillow/search` | `location`, `filters` | Search properties |

### Maintenance Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /actions/androidPhone/maintenance/updateApps` | Install pending updates |
| `GET /actions/androidPhone/maintenance/checkSecurity` | Security patch status |
| `GET /actions/androidPhone/maintenance/clearCache` | Clear app caches |
| `GET /actions/androidPhone/maintenance/reboot` | Reboot device |
| `GET /actions/androidPhone/maintenance/runMonthly` | Run full monthly check |

---

## Security & Safety

### Authentication
- All endpoints require `X-API-Key` header
- USB mode: phone is only reachable by the host via `/dev/bus/usb` passthrough
- Wireless debugging mode: restrict to local network (e.g. 10.0.0.0/24); ADB port 5555 must NOT be exposed to the internet

### Approval Requirements

Actions requiring human approval (via jorb system):
- Uber rides over $50
- Food orders over $75
- Any purchase/payment action
- App installations
- System updates

### Audit Logging

All phone actions logged to:
- `progress_log` - Human-readable summary
- `jorbs.db` - If action creates/uses a jorb
- `app.log` - Detailed technical logs

### Rate Limiting
- Max 10 phone actions per minute
- Max 100 phone actions per hour
- Cooldown after errors

---

## Error Recovery

### Common Error Patterns

| Error | Detection | Recovery |
|-------|-----------|----------|
| App not responding | No UI change after action | Force close, relaunch |
| Wrong screen | Expected element not found | Press back, retry |
| Login required | Login UI detected | Pause, notify user |
| Connection lost | ADB timeout | Reconnect, retry |
| Device locked | Lock screen detected | Wake + swipe unlock |
| App crashed | Crash dialog detected | Dismiss, relaunch |

### Retry Policy
- Max 3 retries per action
- Exponential backoff: 1s, 2s, 4s
- After 3 failures: pause task, notify user

---

## Testing Strategy

### Unit Tests
- Mock ADB responses
- Test prompt template loading
- Test action parsing

### Integration Tests
- Real device connection
- Launch app, verify screen
- Execute simple workflow

### End-to-End Tests
- Full thermostat set/get cycle
- Uber ride request (cancel before confirm)
- Screenshot capture and verification

---

## MVP Implementation Order

### Phase 1: Core Infrastructure
1. `androidPhoneGetScreen` - Screenshot + XML diagnostic
2. `androidPhone_status` - Connection check
3. `AndroidPhoneRunner` - Basic LLM loop

### Phase 2: Thermostat MVP
4. `thermostat-setRange.md` prompt template
5. `thermostat-getStatus.md` prompt template
6. `androidPhone_thermostat_setRange` action
7. `androidPhone_thermostat_getStatus` action

### Phase 3: Maintenance
8. `androidPhone_health` - Full health check
9. Monthly maintenance jorb
10. Weekly health check jorb

### Phase 4: Additional Apps
11. Uber actions
12. Uber Eats actions
13. OpenTable actions
14. AA actions
15. Zillow actions

---

## Future Enhancements

1. **Vision Model Integration** - Use GPT-4V/Claude Vision for complex UIs
2. **Screen Recording** - Video capture for debugging
3. **Multi-Device Support** - Control multiple phones
4. **Custom App Training** - Learn new apps from demonstration
5. **Scheduled Actions** - "Order coffee every morning at 7 AM"
6. **Notification Monitoring** - React to phone notifications
7. **SMS/Call Interception** - Handle 2FA codes automatically
