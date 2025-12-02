# Project Schedule & Estimates

**Velocity:** 20 hours / week
**Total Estimated Effort:** ~102 hours
**Estimated Duration:** 5-6 Weeks

---

## Week 1: Ingestion & Storage Foundation (20h)

### Epic: Implement Ingestion Service (16h)
- [ ] **#9 Lightstreamer Client** (Medium, 6h): Implement async client and WebSocket handling.
- [ ] **#12 Repository Integration** (Medium, 4h): Abstract database writes.
- [ ] **#10 Validation Service** (Low, 2h): DRF serializers for incoming data.
- [ ] **#11 Enrichment Service** (Low, 2h): Add metadata (UUIDs, timestamps).
- [ ] **#13 Manual Injection Endpoint** (Low, 2h): Test endpoint for data entry.

### Epic: Implement Storage (Start) (4h)
- [ ] **#16 Hypertable Migration** (Medium, 3h): Setup TimescaleDB hypertables.
- [ ] **#15 Define Models** (Low, 1h): Create Django models for telemetry.

---

## Week 2: Storage Completion & PeeBot Core (20h)

### Epic: Implement Storage (Finish) (9h)
- [ ] **#19 Repository Implementation** (Medium, 4h): Implement actual DB write logic.
- [ ] **#18 Custom Managers** (Medium, 3h): Efficient querying methods.
- [ ] **#17 Retention & Compression** (Low, 2h): Configure TimescaleDB policies.

### Epic: Implement Pee-Bot (Start) (11h)
- [ ] **#22 PeeBot Logic** (High, 6h): Implement detection algorithm (sliding window).
- [ ] **#21 Base Processor** (Medium, 4h): Abstract processor architecture.
- [ ] **#26 Processor Models** (Low, 1h): Database models for events.

---

## Week 3: PeeBot Wrap-up & Dashboard Start (20h)

### Epic: Implement Pee-Bot (Finish) (7h)
- [ ] **#23 Twitter Integration** (Low, 3h): API client implementation.
- [ ] **#24 Joke Generator** (Low, 2h): Humor service.
- [ ] **#25 Celery Tasks** (Low, 2h): Periodic task scheduling.

### Epic: Add Dashboard (Start) (13h)
- [ ] **#30 WebSocket Consumers** (High, 6h): Real-time data broadcasting.
- [ ] **#28 WebSocket Setup** (Medium, 4h): Channels & Redis configuration.
- [ ] **#29 Dashboard Views** (Medium, 3h): Core HTTP views.

---

## Week 4: Dashboard Completion & Testing Start (20h)

### Epic: Add Dashboard (Finish) (9h)
- [ ] **#32 Chart.js Integration** (Medium, 5h): Frontend visualization logic.
- [ ] **#31 HTMX Integration** (Medium, 4h): Dynamic updates.

### Epic: Testing & Optimization (Start) (11h)
- [ ] **#35 Latency Optimization** (High, 6h): Query and ingestion tuning.
- [ ] **#34 Load Testing** (Medium, 4h): Simulating 10k msg/sec.
- [ ] **#37 Error Tracking** (Low, 1h): Sentry setup.

---

## Week 5: Testing & Deployment (22h)

### Epic: Testing & Optimization (Finish) (10h)
- [ ] **#38 Unit & Integration Tests** (High, 8h): Critical path coverage.
- [ ] **#36 Monitoring Setup** (Low, 2h): Prometheus/Grafana.

### Epic: Deployment (12h)
- [ ] **#40 VPS Configuration** (Medium, 3h): Server setup.
- [ ] **#41 Coolify Setup** (Medium, 3h): Deployment platform.
- [ ] **#42 Reverse Proxy** (Low, 2h): Nginx config.
- [ ] **#43 Production Config** (Low, 2h): Env vars and security.
- [ ] **#44 Systemd Services** (Low, 2h): Process management.
