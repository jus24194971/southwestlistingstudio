/**
 * Utility helpers: DOM, fetch, formatting.
 *
 * Everything here is stateless and reusable across views.
 */

(function () {
    "use strict";

    // ----- DOM -----

    LS.$ = (id) => document.getElementById(id);

    LS.el = function (tag, className, text) {
        const e = document.createElement(tag);
        if (className) e.className = className;
        if (text !== undefined) e.textContent = text;
        return e;
    };

    LS.escapeHTML = function (str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    };

    // ----- Fetch -----

    LS.api = async function (method, path, body) {
        const options = { method, headers: {} };
        if (body !== undefined) {
            options.headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(body);
        }
        const response = await fetch(path, options);
        if (!response.ok) {
            const text = await response.text();
            throw new Error(`${method} ${path} -> ${response.status}: ${text}`);
        }
        if (response.status === 204) return null;
        return response.json();
    };

    // ----- Formatting -----

    LS.dollars = function (cents) {
        if (cents == null) return "—";
        return "$" + (cents / 100).toFixed(2);
    };

    LS.dollarsPlain = function (cents) {
        if (cents == null) return "";
        return (cents / 100).toFixed(2);
    };

    LS.parseDollars = function (str) {
        if (!str) return 0;
        const num = parseFloat(str.toString().replace(/[^\d.]/g, ""));
        if (isNaN(num)) return 0;
        return Math.round(num * 100);
    };

    LS.timeAgo = function (isoString) {
        if (!isoString) return "Never posted";
        const then = new Date(isoString);
        const seconds = Math.floor((Date.now() - then.getTime()) / 1000);
        if (seconds < 60) return "Just now";
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        if (days < 30) return `${days}d ago`;
        const months = Math.floor(days / 30);
        return `${months}mo ago`;
    };

    LS.daysSince = function (isoString) {
        if (!isoString) return null;
        const then = new Date(isoString);
        return Math.floor((Date.now() - then.getTime()) / (24 * 60 * 60 * 1000));
    };

    LS.formatDate = function (isoString) {
        if (!isoString) return "";
        const date = new Date(isoString);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        const dateOnly = new Date(date);
        dateOnly.setHours(0, 0, 0, 0);

        if (dateOnly.getTime() === today.getTime()) return "Today";
        if (dateOnly.getTime() === yesterday.getTime()) return "Yesterday";

        return date.toLocaleDateString("en-US", {
            weekday: "long",
            month: "long",
            day: "numeric",
        });
    };

    LS.formatTime = function (isoString) {
        if (!isoString) return "";
        return new Date(isoString).toLocaleTimeString("en-US", {
            hour: "numeric",
            minute: "2-digit",
        });
    };

    // ----- Platform metadata -----

    LS.platformDisplay = function (p) {
        return ({
            reverb: "Reverb",
            ebay: "eBay",
            etsy: "Etsy",
            squarespace: "Squarespace",
            facebook: "Facebook Marketplace",
        })[p] || p;
    };

    LS.platformLogoText = function (p) {
        return ({
            reverb: "R",
            ebay: "e",
            etsy: "e",
            squarespace: "SQ",
            facebook: "f",
        })[p] || "?";
    };

    LS.setStatus = function (message, mode) {
        const msg = LS.$("status-message");
        const indicator = LS.$("connection-indicator");
        if (msg) msg.textContent = message;
        if (indicator) {
            if (mode === "error") {
                indicator.classList.add("error");
                indicator.querySelector(".conn-text").textContent = "Backend Error";
            } else {
                indicator.classList.remove("error");
                indicator.querySelector(".conn-text").textContent = "Connected";
            }
        }
    };
})();
