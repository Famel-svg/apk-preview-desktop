using System;
using System.Diagnostics;
using System.IO;

internal static class DesktopLauncher
{
    private static int Main()
    {
        string executableDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string projectRoot = Path.GetFullPath(Path.Combine(executableDirectory, "..", ".."));
        string pythonw = Path.Combine(projectRoot, ".venv", "Scripts", "pythonw.exe");

        if (!File.Exists(pythonw))
        {
            return 2;
        }

        var start = new ProcessStartInfo
        {
            FileName = pythonw,
            Arguments = "-m apk_preview.desktop",
            WorkingDirectory = projectRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
        };

        string sdk = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Android",
            "Sdk"
        );
        start.EnvironmentVariables["ANDROID_HOME"] = sdk;
        start.EnvironmentVariables["ANDROID_SDK_ROOT"] = sdk;

        Process process = Process.Start(start);
        return process == null ? 3 : 0;
    }
}
