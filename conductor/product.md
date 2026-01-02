# Product Guide

## Initial Concept
PeeBot is a Django modular monolith for ISS telemetry analytics (TimescaleDB), specifically detecting Urine Processor Assembly activity (NODE3000004) to post humorous tweets.

## Target Audience
The primary audience consists of space enthusiasts and the general public on Twitter who appreciate a blend of space science and humor.

## Core Goals
1.  **Engagement:** Create entertaining, humorous content derived from actual ISS telemetry events.
2.  **Architecture:** Demonstrate a robust, scalable Django Modular Monolith architecture backed by TimescaleDB for handling high-frequency data.

## MVP Features
-   **Ingestion:** Real-time ingestion of Lightstreamer data for the UPA (Urine Processor Assembly).
-   **Analytics:** Reliable detection of "Pee Events" using sliding window analytics on the incoming telemetry stream.
-   **Automation:** An automated tweeting mechanism triggered specifically by detected events.

## Tone & Personality
The bot's persona is humorous and slightly irreverent (e.g., "Somebody's busy up there! 🚽"), aiming to make mundane telemetry data fun and relatable.

## Constraints & System Requirements
-   **Autonomy:** The system must be fully autonomous, requiring no manual intervention from data ingestion to social media posting.
-   **Anti-Spam:** Strict rate limits must be implemented to prevent flooding feeds during periods of high sensor activity.
-   **Performance:** The system requires low latency, with ingestion-to-detection time under 2 minutes.
