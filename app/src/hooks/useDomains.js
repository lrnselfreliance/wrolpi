import {useEffect, useState} from "react";
import {fetchDomains} from "../api";

export const useDomains = () => {
    const [domains, setDomains] = useState(null);
    const [total, setTotal] = useState(null);

    const _fetchDomains = async () => {
        setDomains(null);
        setTotal(0);
        let [domains, total] = await fetchDomains();
        setDomains(domains);
        setTotal(total);
    }

    useEffect(() => {
        _fetchDomains();
    }, []);

    return [domains, total];
}
