change mtu and rollback:  
    junos.install_config:    
        - name: salt://templates/junos/mtu.set    
        - comment: "configured using SaltStack"    
        - replace: False     
        - overwrite: False    
        - confirm: 2

