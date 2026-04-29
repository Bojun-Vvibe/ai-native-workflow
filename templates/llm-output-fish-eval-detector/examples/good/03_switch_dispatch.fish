function safe_dispatch
    switch $argv[1]
        case build
            make all
        case test
            make test
        case '*'
            echo "unknown subcommand"
            return 1
    end
end
