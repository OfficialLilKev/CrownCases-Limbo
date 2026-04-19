# 👑 CrownCases – Limbo Game

A fully interactive, provably fair **Limbo casino game** built with pure **HTML, CSS, and JavaScript**.

This project replicates a modern crypto-style gambling experience with smooth animations, real-time probability calculations, and a provably fair system.

---

## 🎮 Features

### 🎯 Core Gameplay

* Adjustable **bet amount** ($1 – $500)
* Custom **target multiplier** (1.09× – 1,000,000×)
* Real-time **win chance calculation**
* Instant **profit preview**
* Smooth animated **rolling multiplier system**
* Manual + Auto betting modes

---

### ⚡ Game Mechanics

* **95% RTP (5% house edge)**
* Formula:

  ```
  multiplier = 0.95 / (1 - u)
  ```
* Win probability:

  ```
  P(win) = 95 / target_multiplier
  ```

---

### 🔐 Provably Fair System

* Uses:

  * **Client Seed**
  * **Server Seed**
  * **Nonce**
* Roll generation:

  ```
  HMAC-SHA256(serverSeed, clientSeed:nonce)
  ```
* Includes:

  * Server seed hash (pre-commitment)
  * Seed reveal system
  * Roll verification tool built into UI

---

### 📊 Statistics Tracking

* Session Wins / Losses
* Total Wagered
* Net Profit & Loss
* Win Streak
* Best Multiplier
* Last Win

---

### 📜 Bet History

* Full bet log with:

  * Bet amount
  * Target multiplier
  * Rolled result
  * Profit/Loss
* Live history strip (last 50 rolls)

---

### 🤖 Auto Betting

* Set:

  * Number of bets
  * Delay between bets
* Live progress tracking
* Stop anytime

---

### 🎨 UI & UX

* Modern dark-themed casino design
* Responsive layout
* Smooth animations:

  * Rolling multiplier
  * Win/Loss effects
  * Particle confetti on wins
* Sound effects:

  * Win / Loss / Roll ticking
* Fully customizable settings:

  * Sound toggles
  * Volume control
  * Fast roll mode
  * Particle effects toggle

---

## 🚀 Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/crowncases-limbo.git
```

### 2. Open the game

Simply open the HTML file:

```bash
index.html
```

No build step required — runs directly in your browser.

---

## 🧠 How It Works

1. A random float `u` is generated using HMAC-SHA256
2. The multiplier is calculated using:

   ```
   multiplier = 0.95 / (1 - u)
   ```
3. If:

   ```
   rolled_multiplier >= target_multiplier
   ```

   → You win

---

## ⚠️ Disclaimer

This project is for:

* Educational purposes
* UI/UX demonstrations
* Game logic simulation

It does **NOT** include:

* Real money transactions
* Backend or wallet integration
* Security for production gambling use

---

## 🛠 Tech Stack

* **HTML5**
* **CSS3 (Custom properties, animations)**
* **Vanilla JavaScript**
* **Web Crypto API (HMAC + SHA256)**

---

## 💡 Future Improvements

* Backend integration (Node.js / Firebase)
* Real user accounts & authentication
* Crypto wallet support
* Multiplayer / live bets feed
* Leaderboards
* Mobile app version

---

## 📸 Preview

> Clean UI, real-time gameplay, and smooth animations inspired by modern crypto casinos.

---

## 🧑‍💻 Author

Built for the **CrownCases** project.
