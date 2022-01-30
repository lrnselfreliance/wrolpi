import {useEffect, useState} from "react";
import {getVersion} from "../api";

export const useVersion = () => {
    const [version, setVersion] = useState('');

    const fetchVersion = async () => {
        let version = await getVersion();
        setVersion(version);
    }

    useEffect(() => {
        fetchVersion();
    })

    return version;
}
