{ config, lib, pkgs, ... }:
let
  cfg = config.services.ldbgames-server;
in
{
  options.services.ldbgames-server = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Enable LDBGames server";
    };
    port = lib.mkOption {
      type = lib.types.str;
      default = "8000";
      description = "Port the server listens on";
    };
    dataDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/ldbgames-server";
      description = "Directory to store game data";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.ldbgames-server = {
      description = "LDBGames Server";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      serviceConfig = {
        ExecStart = "${pkgs.ldbgames-server}/bin/ldbgames-server";
        Restart = "always";
        Environment = ''
          LDBGAMES_DATADIR=${cfg.dataDir}
        '';
      };
    };

    services.nginx.enable = true;
    services.nginx.virtualHosts."ldbgames.com" = {
      listen = [ { addr = "*"; port = 80; } ];
      locations."/api" = {
        proxyPass = "http://127.0.0.1:${cfg.port}";
      };
    };
  };
}
