import { useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import type { RecordingStatus } from "@voice-to-pdf/types";

export default function HomeScreen() {
  const [status, setStatus] = useState<RecordingStatus>("idle");

  const toggle = () =>
    setStatus((s) => (s === "recording" ? "idle" : "recording"));

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Voice to PDF</Text>
      <Text style={styles.subtitle}>Tap to start recording</Text>

      <TouchableOpacity
        style={[styles.button, status === "recording" && styles.buttonActive]}
        onPress={toggle}
        activeOpacity={0.8}
      >
        <Text style={styles.buttonText}>
          {status === "recording" ? "Stop" : "Record"}
        </Text>
      </TouchableOpacity>

      <Text style={styles.status}>
        Status: <Text style={styles.statusValue}>{status}</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#f9fafb",
    padding: 24,
    gap: 12,
  },
  title: {
    fontSize: 32,
    fontWeight: "700",
    color: "#111827",
  },
  subtitle: {
    fontSize: 16,
    color: "#6b7280",
    marginBottom: 36,
  },
  button: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: "#3b82f6",
    alignItems: "center",
    justifyContent: "center",
  },
  buttonActive: {
    backgroundColor: "#ef4444",
  },
  buttonText: {
    color: "#fff",
    fontSize: 18,
    fontWeight: "600",
  },
  status: {
    marginTop: 24,
    fontSize: 14,
    color: "#9ca3af",
  },
  statusValue: {
    fontWeight: "600",
    color: "#6b7280",
  },
});
