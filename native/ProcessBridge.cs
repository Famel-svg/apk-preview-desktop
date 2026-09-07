using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

internal static class ProcessBridge
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetDllDirectory(string pathName);

    private static string Quote(string value)
    {
        if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) < 0)
            return value;

        var result = new StringBuilder("\"");
        var slashes = 0;
        foreach (var character in value)
        {
            if (character == '\\')
            {
                slashes++;
                continue;
            }

            if (character == '"')
            {
                result.Append('\\', slashes * 2 + 1);
                result.Append('"');
            }
            else
            {
                result.Append('\\', slashes);
                result.Append(character);
            }
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        result.Append('"');
        return result.ToString();
    }

    public static int Main(string[] args)
    {
        if (args.Length == 0)
        {
            Console.Error.WriteLine("ProcessBridge: executable missing.");
            return 64;
        }

        SetDllDirectory(null);
        var info = new ProcessStartInfo
        {
            FileName = args[0],
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = Environment.CurrentDirectory,
        };

        var arguments = new StringBuilder();
        for (var index = 1; index < args.Length; index++)
        {
            if (arguments.Length > 0)
                arguments.Append(' ');
            arguments.Append(Quote(args[index]));
        }
        info.Arguments = arguments.ToString();

        using (var process = Process.Start(info))
        {
            var stdout = process.StandardOutput.BaseStream.CopyToAsync(Console.OpenStandardOutput());
            var stderr = process.StandardError.BaseStream.CopyToAsync(Console.OpenStandardError());
            process.WaitForExit();
            Task.WaitAll(stdout, stderr);
            return process.ExitCode;
        }
    }
}
