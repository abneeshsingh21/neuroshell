// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt
using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

namespace NeuroShell.NativeHost
{
    class Program
    {
        // Win32 Console API for Virtual Terminal Processing
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern IntPtr GetStdHandle(int nStdHandle);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);

        const int STD_OUTPUT_HANDLE = -11;
        const uint ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004;
        const string PIPE_NAME = "neuroshell_ipc";

        // ANSI TrueColor Styling Tokens
        const string C_CYAN = "\u001b[38;2;56;189;248m";
        const string C_MAGENTA = "\u001b[38;2;192;132;252m";
        const string C_GREEN = "\u001b[38;2;74;222;128m";
        const string C_YELLOW = "\u001b[38;2;251;191;36m";
        const string C_MUTED = "\u001b[38;2;100;116;139m";
        const string C_WHITE = "\u001b[38;2;241;245;249m";
        const string C_BOLD = "\u001b[1m";
        const string C_RESET = "\u001b[0m";

        static void EnableVTMode()
        {
            try
            {
                IntPtr hOut = GetStdHandle(STD_OUTPUT_HANDLE);
                if (hOut != IntPtr.Zero)
                {
                    uint mode;
                    if (GetConsoleMode(hOut, out mode))
                    {
                        SetConsoleMode(hOut, mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING | 0x0008);
                    }
                }
            }
            catch { }
        }

        static void PrintBanner()
        {
            Console.WriteLine(C_CYAN + "╔══════════════════════════════════════════════════════════════╗");
            Console.WriteLine("║   " + C_BOLD + C_WHITE + "🧠 NeuroShell" + C_RESET + C_MAGENTA + " v5.0.6" + C_CYAN + " — Native AI Intelligent Terminal          ║");
            Console.WriteLine("║   " + C_MUTED + "Sub-2ms Native Host • 4-Layer Safety • Multi-LLM Router" + C_CYAN + "    ║");
            Console.WriteLine("╚══════════════════════════════════════════════════════════════╝" + C_RESET + "\n");
        }

        static void Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            Console.Title = "NeuroShell v5.0.6 — AI Terminal";
            EnableVTMode();

            PrintBanner();

            while (true)
            {
                string cwd = Directory.GetCurrentDirectory();
                string gitBranch = GetGitBranch();
                string branchTag = string.IsNullOrEmpty(gitBranch) ? "" : " (" + C_MAGENTA + gitBranch + C_MUTED + ")";

                Console.Write(C_CYAN + "🧠 " + C_MUTED + cwd + branchTag + " " + C_CYAN + "❯" + C_RESET + " ");
                string input = Console.ReadLine();

                if (input == null) break;
                input = input.Trim();
                if (string.IsNullOrEmpty(input)) continue;

                if (input.Equals("exit", StringComparison.OrdinalIgnoreCase) ||
                    input.Equals("quit", StringComparison.OrdinalIgnoreCase) ||
                    input.Equals("q", StringComparison.OrdinalIgnoreCase))
                {
                    break;
                }

                // Handle CD internally
                if (input.StartsWith("cd ", StringComparison.OrdinalIgnoreCase) || input.Equals("cd", StringComparison.OrdinalIgnoreCase))
                {
                    string target = input.Length > 3 ? input.Substring(3).Trim() : "";
                    if (string.IsNullOrEmpty(target) || target == "~")
                    {
                        target = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                    }
                    try
                    {
                        Directory.SetCurrentDirectory(Path.GetFullPath(target));
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine("  " + C_YELLOW + "❌ Directory error: " + ex.Message + C_RESET);
                    }
                    continue;
                }

                // Handle Clear Screen
                if (input.Equals("cls", StringComparison.OrdinalIgnoreCase) || input.Equals("clear", StringComparison.OrdinalIgnoreCase))
                {
                    Console.Clear();
                    PrintBanner();
                    continue;
                }

                // Slash command or Natural Language command
                if (input.StartsWith("/") || IsNaturalLanguage(input))
                {
                    ExecuteSlashOrAI(input);
                }
                else
                {
                    // Direct Native Shell Command
                    ExecuteNativeCommand(input);
                }
            }
        }

        static bool IsNaturalLanguage(string input)
        {
            // If the input has spaces and starts with typical natural language trigger words
            string[] nlTriggers = new string[] {
                "find", "search", "show", "list", "how", "what", "create", "make",
                "delete", "remove", "commit", "push", "pull", "clone", "install",
                "run", "kill", "stop", "explain", "fix", "undo", "count", "check"
            };

            string lower = input.ToLower();
            string firstWord = lower.Split(' ')[0];

            // If it's a known exact binary or script in path, execute native
            if (File.Exists(firstWord) || File.Exists(firstWord + ".exe") || File.Exists(firstWord + ".bat") || File.Exists(firstWord + ".cmd"))
            {
                return false;
            }

            foreach (string trig in nlTriggers)
            {
                if (lower.StartsWith(trig + " ") && input.Contains(" "))
                {
                    // Heuristic: Multiple words starting with action verb
                    return true;
                }
            }

            return false;
        }

        static void ExecuteNativeCommand(string command)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("cmd.exe", "/c " + command)
                {
                    UseShellExecute = false
                };
                using (Process proc = Process.Start(psi))
                {
                    proc.WaitForExit();
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("  " + C_YELLOW + "❌ Execution failed: " + ex.Message + C_RESET);
            }
        }

        static void ExecuteSlashOrAI(string input)
        {
            try
            {
                using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", PIPE_NAME, PipeDirection.InOut))
                {
                    pipe.Connect(500); // 500ms timeout
                    string method = input.StartsWith("/") ? "slash" : "translate";
                    string paramKey = input.StartsWith("/") ? "command" : "query";
                    string escapedInput = input.Replace("\\", "\\\\").Replace("\"", "\\\"");

                    string json = "{\"jsonrpc\":\"2.0\",\"method\":\"" + method + "\",\"params\":{\"" + paramKey + "\":\"" + escapedInput + "\",\"cwd\":\"" + Directory.GetCurrentDirectory().Replace("\\", "\\\\") + "\"},\"id\":1}\n";
                    byte[] data = Encoding.UTF8.GetBytes(json);
                    pipe.Write(data, 0, data.Length);
                    pipe.Flush();

                    byte[] buffer = new byte[65536];
                    int bytesRead = pipe.Read(buffer, 0, buffer.Length);
                    if (bytesRead > 0)
                    {
                        string responseJson = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                        // If it's a translated command, display and execute
                        if (method == "translate" && responseJson.Contains("\"command\""))
                        {
                            string cmd = ExtractJsonValue(responseJson, "command");
                            if (!string.IsNullOrEmpty(cmd))
                            {
                                Console.WriteLine("  " + C_GREEN + "✔ Transformed → " + C_BOLD + C_WHITE + cmd + C_RESET);
                                ExecuteNativeCommand(cmd);
                                return;
                            }
                        }
                    }
                }
            }
            catch
            {
                // If IPC daemon is not active, fallback directly to Python backend
                ExecuteNativeCommand("python main.py \"" + input + "\"");
            }
        }

        static string ExtractJsonValue(string json, string key)
        {
            string pattern = "\"" + key + "\":\"";
            int idx = json.IndexOf(pattern);
            if (idx == -1) return "";
            int start = idx + pattern.Length;
            int end = json.IndexOf("\"", start);
            if (end == -1) return "";
            return json.Substring(start, end - start).Replace("\\\"", "\"").Replace("\\\\", "\\");
        }

        static string GetGitBranch()
        {
            try
            {
                if (File.Exists(".git/HEAD"))
                {
                    string head = File.ReadAllText(".git/HEAD").Trim();
                    if (head.StartsWith("ref: refs/heads/"))
                    {
                        return head.Substring("ref: refs/heads/".Length);
                    }
                }
            }
            catch { }
            return "";
        }
    }
}
